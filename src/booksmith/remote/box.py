"""Транспорт до арендованной машины: ssh для команд, rsync для файлов.

rsync, а не scp с tar в конце, ровно по одной причине: он инкрементальный.
Раньше результат паковался архивом после того, как задача досчитает всё, и
падение на 400-й странице из 539 теряло всё.  Здесь `outputs/` подтягивается
по ходу работы, и упавший прогон оставляет то, что успел посчитать.
"""
import os
import re
import select
import shlex
import subprocess
import tempfile
import threading
import time

# Одно соединение на все обращения к машине.  Замер: заливка пяти файлов — это
# пять отдельных rsync, то есть пять рукопожатий по 4-5 секунд, и файл в 10 КБ
# стоит столько же, сколько 4.4 МБ.  За трёхпроходный прогон набегает 21
# рукопожатие.  Мультиплексирование сводит их к одному на машину.
#
# Сокет лежит в СВОЁМ каталоге, а не прямо в /tmp, и это не гигиена, а защита
# от отказа, роняющего оплаченный прогон.  Проверено запуском: если файл на
# пути сокета принадлежит другому пользователю, ssh НЕ переходит тихо на
# обычное соединение, а валит его целиком:
#
#     unix_listener: cannot bind to path /tmp/.booksmith-… Permission denied
#     rc=255
#
# В общем /tmp с липким битом это ровно случай «однажды запустили под sudo»:
# все последующие прогоны падали бы уже ПОСЛЕ съёма машины, то есть на
# тарифицируемой карте.  Своим каталогом с режимом 0700 закрывается заодно и
# подставной сокет: ssh не проверяет ни владельца, ни права уже существующего
# сокета, а имя пути угадывается снаружи, и сокет, который принимает и молчит,
# вешает ssh без всякого таймаута.
#
# Длина пути к юникс-сокету ограничена 108 байтами (проверено `bind()`);
# худший реальный случай с числовым адресом и портом — 47 байт (в прежнем
# счёте стояло 42: забыли пятизначный порт), запас
# двукратный.
_SOCK_DIR = os.path.join(tempfile.gettempdir(), f".booksmith-{os.getuid()}")
try:
    os.makedirs(_SOCK_DIR, mode=0o700, exist_ok=True)
except OSError:
    _SOCK_DIR = tempfile.gettempdir()

SSH_OPTS = [
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath={_SOCK_DIR}/%r@%h:%p",
    "-o", "ControlPersist=180",
    # Без этого ssh к замолчавшей машине висит бесконечно — проверено и с
    # мультиплексированием, и без него.  Мультиплексирование не создаёт
    # зависание, но удлиняет его почти на полторы минуты.
    "-o", "ConnectTimeout=15",
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
        self._stop_hb = threading.Event()
        self._hb_thread: threading.Thread | None = None

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
    def probe(self, mb: int = 4, timeout: float = 25.0) -> float:
        """Сколько Мбит/с реально даёт канал до этой машины.

        Заявленные хостом мегабиты — про его собственный доступ в интернет, а
        не про путь до нас.  Разница бывает катастрофической: машина с
        обещанными 1188 Мбит/с приняла 3.5 МБ входного файла за семь с
        половиной минут (62 кбит/с), причём с PyPI качала нормально.
        Пятнадцать минут и деньги ушли впустую, и узнали мы это только когда
        задача не начиналась.

        Двадцать секунд здесь отсеивают такую машину до того, как на неё
        что-то зальют.  Данные берём из /dev/urandom — нули сжались бы в
        транспорте ssh и дали бы красивую неправду.
        """
        cmd = self._ssh + [self._addr, f"head -c {mb * 1024 * 1024} /dev/urandom"]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 0.0
        dt = max(time.time() - t0, 1e-6)
        got = len(p.stdout)
        if p.returncode != 0 or got < mb * 1024 * 1024 // 2:
            return 0.0
        return got * 8 / 1e6 / dt

    def probe_download(self, mb: int = 12, streams: int = 6,
                       timeout: float = 40.0) -> float:
        """Сколько Мбит/с машина вытягивает из мира, В НЕСКОЛЬКО ПОТОКОВ.

        Потоков несколько намеренно: uv качает колёса в десятки соединений,
        и однопоточный замер с этим не связан вовсе.  Первая версия зонда
        мерила один поток на 8 МБ — почти сплошной разгон TCP — и дала
        обратную зависимость: 154 Мбит/с на машине, где колёса встали за
        104 с, и 307 на машине, где те же колёса заняли 277 с.

        Число пока только записывается в журнал.  Порог для отбраковки
        поставим, когда наберётся достаточно пар «зонд — время колёс»:
        ставить его по двум точкам — это ровно та ошибка, что уже была.
        """
        url = ("https://files.pythonhosted.org/packages/source/n/numpy/"
               "numpy-2.2.0.tar.gz")
        chunk = mb * 1024 * 1024
        # -L обязателен: pythonhosted отвечает 302 на этот путь, и без него
        # curl молча скачивает ноль байт, а машина выглядит сломанной.
        parts = " ".join(
            f"curl -sSL -o /dev/null --max-time {int(timeout)} "
            f"-r {i * chunk}-{(i + 1) * chunk - 1} {url} &"
            for i in range(streams))
        cmd = (f"S=$(date +%s%N); {parts} wait; E=$(date +%s%N); "
               f"echo $(( {chunk * streams} * 8000 / (E - S) ))")
        rc, out = self.run(cmd, stream=False,
                           deadline=time.time() + timeout + 20)
        try:
            return float(out.strip().splitlines()[-1])
        except Exception:
            return 0.0

    # Потолок на одну передачу.  Полчаса с запасом покрывают худшее из
    # виденного: 180 МБ картинок при канале 2.9 Мбит/с — это около шестнадцати
    # минут.  Раньше потолка не было вовсе, и зависший rsync висел вечно:
    # поток фоновой синхронизации не выходил, `stop_sync` жёг свои триста
    # секунд впустую, а финальная выкачка не кончалась никогда.
    RSYNC_TIMEOUT_S = 1800

    def _rsync(self, src: str, dst: str, extra: list[str] | None = None,
               timeout: float | None = None) -> int:
        rsh = " ".join(shlex.quote(x) for x in
                       ["ssh", "-p", self.port] + SSH_OPTS +
                       (["-i", self.key] if self.key else []))
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + (extra or []) + [src, dst]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout or self.RSYNC_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # `--partial` оставляет недокачанное на месте, так что следующая
            # попытка продолжит, а не начнёт заново.
            log(f"  rsync не уложился в "
                f"{(timeout or self.RSYNC_TIMEOUT_S)/60:.0f} мин — прерван")
            return 124
        if p.returncode != 0:
            log(f"  rsync: {p.stderr.strip()[:200]}")
        return p.returncode

    _STAT_SIZE = re.compile(r"Total transferred file size:\s*([\d,]+)")
    _STAT_FILES = re.compile(r"Number of files:\s*[\d,]+\s*\(reg:\s*([\d,]+)")

    def _dry_stats(self, src: str, dst: str, exclude=()):
        """Сколько байт и файлов уехало бы. Считает сам rsync, вхолостую."""
        extra = ["--dry-run", "--stats"] + [f"--exclude={x}" for x in exclude]
        rsh = " ".join(shlex.quote(x) for x in
                       ["ssh", "-p", self.port] + SSH_OPTS +
                       (["-i", self.key] if self.key else []))
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + extra + [src, dst]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return None
        if p.returncode != 0:
            return None
        m1 = self._STAT_SIZE.search(p.stdout)
        m2 = self._STAT_FILES.search(p.stdout)
        if not m1:
            return None
        return (int(m1.group(1).replace(",", "")),
                int(m2.group(1).replace(",", "")) if m2 else -1)

    def weigh_exclude(self, remote_rel: str, exclude: tuple, local_dir: str):
        """Вес каждого исключения в байтах — замер, а не догадка.

        Меряем САМИМ rsync и вхолостую: `--dry-run --stats` без исключений и
        с ними, разница и есть вес.  Не `du` и не `find` по тому же шаблону —
        и вот почему.  Шаблон толкует rsync, и толкует по-своему:
        `pages/*.json` у него не то же, что `pages/**.json`, а `imgs/` не то
        же, что `imgs`.  Мерить одним толкованием, а выгружать другим значит
        получить в журнале красивое число, не имеющее отношения к тому, что
        на самом деле не приехало.  Замер вхолостую стоит одного обхода
        каталога и ноль байт передачи.

        Ради этого всё и затевалось.  `cli.py` исключал у свидетелей
        `pages/*.json` вместе с `imgs/`, и это выглядело разумной экономией,
        пока никто не назвал цену.  Названная цена: json на проводе — 6.55 МБ
        из 822, то есть 0.8% выгрузки, потому что rsync жмёт json в 6.9 раза,
        а картинки в 1.04.  За эти 0.8% четыре книги из шести остались без
        постраничной разметки свидетелей — то есть без единственного способа
        узнать, у какого прохода взята страница и где стояли рамки блоков.

        Возвращает список `(шаблон, байт, файлов)` плюс строку «всего».
        """
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        dst = local_dir.rstrip("/") + "/"
        full = self._dry_stats(src, dst)
        if full is None:
            log("  вес исключений измерить не удалось — rsync не ответил")
            return []
        rows = []
        for pat in exclude:
            got = self._dry_stats(src, dst, exclude=(pat,))
            if got is None:
                rows.append((pat, None, None))
                continue
            rows.append((pat, full[0] - got[0], max(full[1] - got[1], 0)))
        kept = self._dry_stats(src, dst, exclude=tuple(exclude)) if exclude else full
        log(f"  выгрузка {remote_rel}: всего {full[0]/1e6:.1f} МБ "
            f"в {full[1]} файлах")
        for pat, b, f in rows:
            if b is None:
                log(f"  исключение {pat}: измерить не удалось")
            else:
                log(f"  исключение {pat}: {b/1e6:.1f} МБ, {f} файлов "
                    f"({100.0*b/max(full[0],1):.1f}% выгрузки) — НЕ ПРИЕДЕТ")
        if kept:
            log(f"  приедет {kept[0]/1e6:.1f} МБ в {kept[1]} файлах")
        return rows

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

    def pull(self, remote_rel: str, local_dir: str, quiet: bool = False,
             exclude: tuple[str, ...] = (), timeout: float | None = None) -> int:
        """Забрать результат.  `exclude` — что не тянуть вовсе.

        Нужно для свидетелей многопроходного разбора: своду от них требуются
        только `pages/*.md` и `book/book.md`, а каталог прохода весит 179 МБ,
        из которых 167 — картинки.  На двух свидетелей это 352 МБ лишнего; при
        канале, какой был в замере (2.9 Мбит/с), — шестнадцать минут передачи
        ни за чем.
        """
        os.makedirs(local_dir, exist_ok=True)
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        extra = [f"--exclude={x}" for x in exclude]
        rc = self._rsync(src, local_dir.rstrip("/") + "/", extra or None,
                         timeout=timeout)
        if rc != 0 and not quiet:
            log(f"  не удалось забрать {remote_rel} (код {rc})")
        return rc

    # ------------------------------------------------------------ пульс
    def start_heartbeat(self, every: float = 30) -> None:
        """Показывать машине, что оператор жив.

        На той стороне за этим файлом следит дозор мертвеца из ONSTART: не
        обновлялся дольше положенного — инстанс уничтожает себя сам.  Без
        пульса выключатель был только у нас, и падение локального процесса
        оставляло машину биллиться в никуда.

        Ошибки касания намеренно проглатываются: одна пропущенная попытка
        ничего не решает (срок — минуты), а ронять из-за неё прогон, который
        считается на машине нормально, было бы глупо.
        """
        def loop():
            while not self._stop_hb.wait(every):
                try:
                    subprocess.run(self._ssh + [self._addr, "touch /root/.alive"],
                                   capture_output=True, timeout=30)
                except Exception:
                    pass
        self._stop_hb.clear()
        self._hb_thread = threading.Thread(target=loop, daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        """Прекратить пульс — обязательно перед тем, как бросить машину.

        Без этого дозор мертвеца выключен ровно там, где он нужнее всего:
        отбракованная по каналу машина, которую не удалось уничтожить,
        продолжала получать пульс от нашего же потока и потому не убивала
        себя сама.  Плюс за пять попыток аренды накапливалось пять потоков,
        четыре из них стучались в мёртвые хосты.
        """
        self._stop_hb.set()
        t = getattr(self, "_hb_thread", None)
        if t is not None and t.is_alive():
            t.join(timeout=2)

    def set_deadman(self, seconds: int) -> None:
        """Переставить срок дозора — например, перед --keep."""
        self.run(f"echo {int(seconds)} > /root/.alive.grace", stream=False)

    # ------------------------------------------------- фоновая синхронизация
    def start_sync(self, remote_rel: str, local_dir: str, every: float = 20,
                   exclude: tuple[str, ...] = ()) -> None:
        """Тянуть результаты по ходу работы, а не только в конце."""
        def loop():
            while not self._stop_sync.wait(every):
                # Фоновой выкачке потолок короче: она всё равно повторится
                # через двадцать секунд, а висеть полчаса ей незачем.
                self.pull(remote_rel, local_dir, quiet=True, exclude=exclude,
                          timeout=300)
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
