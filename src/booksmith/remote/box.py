"""Транспорт до арендованной машины: ssh для команд, rsync для файлов.

rsync, а не scp с tar в конце, ровно по одной причине: он инкрементальный.
Раньше результат паковался архивом после того, как задача досчитает всё, и
падение на 400-й странице из 539 теряло всё.  Здесь `outputs/` подтягивается
по ходу работы, и упавший прогон оставляет то, что успел посчитать.
"""
import os
import select
import shlex
import subprocess
import threading
import time

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "ServerAliveInterval=20",
    "-o", "ServerAliveCountMax=3",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Box:
    """Живая машина, на которой можно выполнять команды и держать файлы."""

    def __init__(self, user: str, host: str, port: str,
                 key: str | None, workdir: str):
        self.user, self.host, self.port = user, host, port
        self.key, self.workdir = key, workdir
        self._stop_sync = threading.Event()
        self._sync_thread: threading.Thread | None = None

    # ------------------------------------------------------------- примитивы
    @property
    def _ssh(self) -> list[str]:
        return ["ssh", "-p", self.port] + SSH_OPTS + (
            ["-i", self.key] if self.key else [])

    @property
    def _addr(self) -> str:
        return f"{self.user}@{self.host}"

    def wait_ready(self, timeout: float = 420) -> None:
        t0, err = time.time(), ""
        while time.time() - t0 < timeout:
            try:
                p = subprocess.run(self._ssh + [self._addr, "true"],
                                   capture_output=True, text=True, timeout=45)
            except subprocess.TimeoutExpired:
                # Пока контейнер поднимается, порт часто просто не отвечает, и
                # ssh висит.  Это нормальное состояние, а не отказ: раньше
                # первая же такая попытка роняла прогон — уже после того, как
                # образ выкачан и оплачен.
                err = "ssh не ответил за 45с"
                continue
            if p.returncode == 0:
                log(f"  ssh готов через {time.time()-t0:.0f}с")
                return
            err = p.stderr.strip()
            time.sleep(8)
        raise RuntimeError(f"ssh на {self.host}:{self.port} так и не поднялся:\n{err}")

    def run(self, cmd: str, stream: bool = True,
            deadline: float | None = None) -> tuple[int, str]:
        """Выполнить команду.  При stream=True вывод идёт к нам построчно.

        `deadline` — абсолютное время (time.time()), после которого команда
        убивается.  Это часть бюджетной защиты: задача не должна пережить
        деньги, которые на неё выделены.
        """
        full = self._ssh + [self._addr, cmd]
        if not stream:
            p = subprocess.run(full, capture_output=True, text=True)
            return p.returncode, p.stdout + p.stderr

        p = subprocess.Popen(full, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        # Читать через `for line in p.stdout` нельзя: строка блокирует до
        # следующего вывода, а задача молчит минутами (vLLM грузит модель,
        # пайплайн инициализируется).  Проверка дедлайна в таком цикле
        # недостижима ровно тогда, когда она нужнее всего.
        try:
            while True:
                ready, _, _ = select.select([p.stdout], [], [], 5.0)
                if ready:
                    line = p.stdout.readline()
                    if not line:
                        break                      # EOF: процесс закончился
                    print("    " + line.rstrip(), flush=True)
                elif p.poll() is not None:
                    break
                if deadline and time.time() > deadline:
                    log("!!! бюджет/таймаут исчерпан — снимаю задачу")
                    p.kill()
                    p.wait(timeout=10)
                    return 124, ""
        finally:
            if p.poll() is None:
                # Нормальный конец: ssh уже закрыл stdout, но ещё не пожат.
                # Убивать здесь сразу — значит превратить успешный прогон в -9.
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
        return p.wait(), ""

    # --------------------------------------------------------------- файлы
    def _rsync(self, src: str, dst: str, extra: list[str] | None = None) -> int:
        rsh = " ".join(shlex.quote(x) for x in
                       ["ssh", "-p", self.port] + SSH_OPTS +
                       (["-i", self.key] if self.key else []))
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + (extra or []) + [src, dst]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            log(f"  rsync: {p.stderr.strip()[:200]}")
        return p.returncode

    def push(self, local: str, remote_rel: str) -> None:
        dst = f"{self._addr}:{self.workdir}/{remote_rel}"
        rc = self._rsync(local, dst)
        if rc != 0:
            # rsync может отсутствовать в образе, несмотря на onstart
            log("  rsync не сработал, падаю обратно на scp")
            cmd = ["scp", "-P", self.port] + SSH_OPTS + (
                ["-i", self.key] if self.key else [])
            if os.path.isdir(local):
                cmd.append("-r")
            cmd += [local, dst]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError(f"заливка {local} не удалась: {p.stderr.strip()}")

    def pull(self, remote_rel: str, local_dir: str, quiet: bool = False) -> int:
        os.makedirs(local_dir, exist_ok=True)
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        rc = self._rsync(src, local_dir.rstrip("/") + "/")
        if rc != 0 and not quiet:
            log(f"  не удалось забрать {remote_rel} (код {rc})")
        return rc

    # ------------------------------------------------- фоновая синхронизация
    def start_sync(self, remote_rel: str, local_dir: str, every: float = 20) -> None:
        """Тянуть результаты по ходу работы, а не только в конце."""
        def loop():
            while not self._stop_sync.wait(every):
                self.pull(remote_rel, local_dir, quiet=True)
        self._stop_sync.clear()
        self._sync_thread = threading.Thread(target=loop, daemon=True)
        self._sync_thread.start()
        log(f"  фоновая синхронизация {remote_rel} -> {local_dir} каждые {every:.0f}с")

    def stop_sync(self) -> None:
        """Дождаться фоновой выкачки прежде, чем начинать финальную.

        Иначе два rsync пишут в один каталог одновременно, а ссылку на поток
        мы теряем.
        """
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=180)
            if self._sync_thread.is_alive():
                log("  фоновая синхронизация всё ещё идёт, жду ещё")
                self._sync_thread.join(timeout=180)
            self._sync_thread = None
