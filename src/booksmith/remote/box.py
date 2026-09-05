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
        # Доклад дозора мертвеца, пока не спрошено — «не проверен».  Пустая
        # строка здесь была бы тем самым нулём от непонимания: «не спрашивали»
        # читалось бы как «не взведён».
        self.deadman = "не проверен"

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
            # `deadline` соблюдается и здесь.  Прежде эта ветка игнорировала
            # его целиком и шла без `timeout`: докстринг обещал бюджетную
            # защиту, а `set_deadman`, `probe_download` и `rm -rf` могли
            # висеть на замолчавшей машине сколько угодно — при работающем
            # счётчике.
            if deadline is not None and deadline <= time.time():
                # Срок вышел ДО запуска — не даём команде одну секунду и не
                # оставляем её сиротой на машине.  Прежняя форма
                # `max(1.0, ...)` запускала ssh, убивала местного клиента по
                # таймауту и уходила дальше, пока удалённая команда
                # продолжала работать.
                return 124, f"срок вышел до запуска: {cmd[:80]}"
            limit = None if deadline is None else deadline - time.time()
            try:
                p = subprocess.run(full, capture_output=True, text=True,
                                   timeout=limit)
            except subprocess.TimeoutExpired:
                # 124 — тот же код, которым отвечает `_rsync` по таймауту.
                return 124, f"ssh не уложился в срок: {cmd[:80]}"
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
    def probe(self, seconds: float = 12.0, mb_cap: int = 64) -> float:
        """Сколько Мбит/с реально даёт канал до этой машины.

        Заявленные хостом мегабиты — про его собственный доступ в интернет, а
        не про путь до нас.  Разница бывает катастрофической: машина с
        обещанными 1188 Мбит/с приняла 3.5 МБ входного файла за семь с
        половиной минут (62 кбит/с), причём с PyPI качала нормально.
        Пятнадцать минут и деньги ушли впустую, и узнали мы это только когда
        задача не начиналась.

        МЕРИМ ЗА ВРЕМЯ, А НЕ ЗА РАЗМЕР, и вот чем обошлось обратное. Прежде
        зонд просил РОВНО 4 МБ и ждал их 25 с; не успел — возвращал 0.0, а
        ноль в `runner` означает «машина сломана». То есть «мы не успели
        принять» записывалось как «она не умеет отдавать», и отличить одно от
        другого было нельзя ПО ПОСТРОЕНИЮ.

        Замер, которым это оплачено — платный прогон 3 сентября 2026: три
        годные машины подряд под нож, $0.081 и 13 минут из 60. Причина
        арифметическая: 4 МБ это 32 Мбит, наш канал 2.8 Мбит/с по HTTP, а
        один поток ssh даёт от него около 41% (1.16 Мбит/с — замер того же
        прогона: 4 МБ не пришли за 27.5 с). Порог же выводился из HTTP-замера
        (`0.5*ours` = 1.42) и стоял ВЫШЕ того, что наша собственная линия
        способна выдать через ssh. Два транспорта, одно число.

        Теперь зонд читает поток столько, сколько отведено, и возвращает
        честную скорость по принятому. Ложных нулей нет вовсе: ноль означает
        «не пришло ни байта», и это уже про машину, а не про нас. Сломанная
        машина с 62 кбит/с отдаст за 12 с около 93 КБ и даст 0.06 Мбит/с —
        ниже любого разумного порога, ровно как и задумано.

        Данные берём из /dev/urandom — нули сжались бы в транспорте ssh и
        дали бы красивую неправду. `mb_cap` только ограничивает поток сверху,
        чтобы не гнать бесконечность: на 64 МБ за 12 с упёрлись бы лишь при
        43 Мбит/с, а такой канал нам и не нужен.
        """
        # ЗОНД НЕ СТАНОВИТСЯ ХОЗЯИНОМ МУЛЬТИПЛЕКСА, и это не мелочь. В
        # `SSH_OPTS` стоит `ControlMaster=auto`: первое соединение становится
        # хозяином общего сокета, и все следующие идут через него. А зонд
        # теперь ЧИТАЕТ ОТВЕДЁННОЕ ВРЕМЯ И УБИВАЕТ ssh — значит, окажись он
        # хозяином, вместе с ним оборвалось бы всё, что пойдёт следом. Именно
        # так и выглядела заливка 87.5 МБ 3 сентября 2026: «rsync: [sender]
        # write error: Broken pipe (32)» через две минуты, падение на scp и
        # потеря `--partial`, то есть возможности продолжить с места обрыва.
        # `ControlMaster=no` — это «пользуйся хозяином, если он есть, но сам
        # им не становись»; своё соединение зонда умирает вместе с ним и
        # ничего за собой не уносит.
        cmd = (self._ssh + ["-o", "ControlMaster=no"]
               + [self._addr, f"head -c {mb_cap * 1024 * 1024} /dev/urandom"])
        t0 = time.time()
        got = 0
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
        try:
            while time.time() - t0 < seconds:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                got += len(chunk)
        finally:
            p.kill()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        dt = max(time.time() - t0, 1e-6)
        return got * 8 / 1e6 / dt

    # Размер пробного файла: диапазоны за его концом отдают 416 и ноль байт.
    # Проверено запросом HEAD 03.09.2026: `content-length: 20225497` после
    # 302 -> 200, то есть число верное и файл на месте.
    PROBE_FILE_BYTES = 20_225_497

    def probe_download(self, streams: int = 6, timeout: float = 40.0) -> float:
        """Сколько Мбит/с машина вытягивает из мира, В НЕСКОЛЬКО ПОТОКОВ.

        Потоков несколько намеренно: uv качает колёса в десятки соединений,
        и однопоточный замер с этим не связан вовсе.  Первая версия зонда
        мерила один поток на 8 МБ — почти сплошной разгон TCP — и дала
        обратную зависимость: 154 Мбит/с на машине, где колёса встали за
        104 с, и 307 на машине, где те же колёса заняли 277 с.

        ДЛИНА КУСКА СЧИТАЕТСЯ ОТ ФАЙЛА, а не задаётся параметром, и вот
        почему.  Стояло `mb=12`, `streams=6`: шесть диапазонов по 12 МиБ
        покрывают 75.5 МБ на файле в 20.2 МБ, то есть первый поток качал
        12.6 МБ, второй — остаток 7.6 МБ, а четыре последних просили за
        концом файла, получали 416 и ноль байт.  «Зонд в шесть потоков» мерил
        ДВА — ровно того, ради чего он переписан, он и не мерил.  Теперь
        `streams` кусков делят файл ровно, и параметр остался один.

        Число пока только записывается в журнал.  Порог для отбраковки
        поставим, когда наберётся достаточно пар «зонд — время колёс»:
        ставить его по двум точкам — это ровно та ошибка, что уже была.
        """
        url = ("https://files.pythonhosted.org/packages/source/n/numpy/"
               "numpy-2.2.0.tar.gz")
        streams = max(1, int(streams))
        chunk = self.PROBE_FILE_BYTES // streams
        # -L обязателен: pythonhosted отвечает 302 на этот путь, и без него
        # curl молча скачивает ноль байт, а машина выглядит сломанной.
        # Считаем ПРИЕХАВШИЕ байты, а не заказанные. Прежняя редакция делила
        # константу `chunk * streams`: диапазоны за концом файла отдают 416,
        # который curl ошибкой не считает.  Машина с закрытым выходом наружу
        # отвечала мгновенно и без единого байта, формула выдавала
        # ~3000 Мбит/с, число уходило в журнал рекордом, и `fast_machines`
        # ставила такую машину первой. Соседний `probe()` сделан правильно;
        # здесь проверки не было вовсе.
        #
        # Последний кусок берёт остаток от деления: при шести потоках это
        # 3 370 916 Б на поток и +1 Б хвоста, весь файл покрыт ровно один раз.
        parts = " ".join(
            f"curl -sSL -o /dev/null --max-time {int(timeout)} "
            f"-w '%{{size_download}}\n' "
            f"-r {i * chunk}-"
            f"{(self.PROBE_FILE_BYTES - 1) if i == streams - 1 else (i + 1) * chunk - 1}"
            f" {url} &"
            for i in range(streams))
        cmd = (f"S=$(date +%s%N); {{ {parts} wait; }} > /tmp/.dl; "
               f"E=$(date +%s%N); "
               f"echo GOT $(awk '{{s+=$1}} END {{print s+0}}' /tmp/.dl) "
               f"NS $(( E - S ))")
        rc, out = self.run(cmd, stream=False,
                           deadline=time.time() + timeout + 20)
        got = ns = 0
        for line in out.splitlines():
            if line.startswith("GOT "):
                try:
                    _, g, _, n = line.split()
                    got, ns = int(g), int(n)
                except Exception:
                    return 0.0
        if ns <= 0:
            return 0.0
        want = self.PROBE_FILE_BYTES
        if got < want * 0.5:
            # Приехало меньше половины заказанного — мерить нечего. Ноль здесь
            # означает «зонд не сработал», и это ЯВНОЕ значение, а не быстрый
            # канал: ноль от проверки и ноль от непонимания — разные нули.
            return 0.0
        return got * 8000.0 / ns

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

        Ради этого всё и затевалось.  Постраничный json исключали заодно с
        картинками, и это выглядело разумной экономией, пока никто не назвал
        цену.  Названная цена: json на проводе — 6.55 МБ из 822, то есть 0.8%
        выгрузки, потому что rsync жмёт json в 6.9 раза, а картинки в 1.04.
        За эти 0.8% четыре книги из шести остались без постраничной
        разметки — то есть без единственного способа узнать, где стояли рамки
        блоков.  Урок общий и схему, ради которой он был получен, пережил:
        исключение, чью цену не назвали числом, дёшево только на вид.

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
        """Положить файл или КАТАЛОГ ровно туда, как он назван.

        `rsync SRC DST` — это не `cp -r`: источник БЕЗ хвостовой косой всегда
        ложится ВНУТРЬ назначения, есть оно уже или нет.  Замер местным rsync
        3.2.7 на каталоге `pkg` с двумя файлами:

            rsync -az --partial src/pkg  d1/pkg   -> d1/pkg/pkg/f.txt
            rsync -az --partial src/pkg  d2/pkg   -> d2/pkg/pkg/f.txt (d2/pkg был)
            rsync -az --partial src/pkg/ d3/pkg/  -> d3/pkg/f.txt      КАК НАДО

        Цена ошибки — вся аренда: задание второго уровня возит на бокс ДВА
        каталога (`src/booksmith` -> `booksmith` и разметку -> `detect`), и
        они легли бы как `/root/job/booksmith/booksmith/…`.  `import
        booksmith` нашёл бы каталог без `__init__.py`, а проверка
        `detect/pages` не нашла бы страниц — оба отказа громкие, но уже после
        девяти гигабайт колёс и подъёма vLLM.  Не всплывало потому, что
        прежнее задание (`dots_ocr`) возило одни файлы: для файла косая не
        нужна и поведение верное.

        У scp семантика ТРЕТЬЯ, и запасной путь надо чинить отдельно.  Замер
        тем же OpenSSH 9.6:

            scp -r src/pkg  s1/pkg  -> s1/pkg/f.txt      (назначения не было)
            scp -r src/pkg  s2/pkg  -> s2/pkg/pkg/f.txt  (назначение было)
            scp -r src/pkg/ s3/pkg  -> s3/pkg/pkg/f.txt  косая НЕ помогает
            scp -r src/pkg/. s4/pkg -> s4/pkg/f.txt      верно в ОБОИХ случаях
        """
        dst = f"{self._addr}:{self.workdir}/{remote_rel}"
        src = local
        if os.path.isdir(local):
            src = local.rstrip("/") + "/"
            dst = dst.rstrip("/") + "/"
        # rsync создаёт только ПОСЛЕДНЕЕ звено пути: `a/b` при отсутствующем
        # `a` — это отказ уже на арендованной машине.  Каталог задачи создан
        # раньше в `execute`, поэтому лишний вызов делаем только для вложенных
        # имён.
        parent = os.path.dirname(remote_rel.rstrip("/"))
        if parent:
            self.run("mkdir -p " + shlex.quote(f"{self.workdir}/{parent}"),
                     stream=False, deadline=time.time() + self.SHORT_CMD_S)
        rc = self._rsync(src, dst)
        if rc != 0:
            # rsync может отсутствовать в образе, несмотря на onstart
            log("  rsync не сработал, падаю обратно на scp")
            cmd = ["scp", "-P", self.port] + SSH_OPTS + (
                ["-i", self.key] if self.key else [])
            scp_src = local
            if os.path.isdir(local):
                cmd.append("-r")
                # `/.` вместо голого каталога: см. замер в докстринге —
                # только эта форма кладёт содержимое и когда назначение уже
                # есть, и когда его нет.
                scp_src = local.rstrip("/") + "/."
            cmd += [scp_src, f"{self._addr}:{self.workdir}/{remote_rel}"]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError(f"заливка {local} не удалась: {p.stderr.strip()}")

    def pull(self, remote_rel: str, local_dir: str, quiet: bool = False,
             exclude: tuple[str, ...] = (), timeout: float | None = None) -> int:
        """Забрать результат.  `exclude` — что не тянуть вовсе.

        Нужно, когда каталог результата в основном состоит из того, что нам
        не нужно.  Замер прежнего прогона: каталог весил 179 МБ,
        из которых 167 — картинки; при канале, какой был в замере
        (2.9 Мбит/с), это шестнадцать минут передачи ни за чем.
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

    # Потолок короткой служебной команды.  Минуты хватает с запасом на
    # `echo`+`mv` через уже поднятое мультиплексированное соединение, а вот
    # без потолка `set_deadman` зовётся из `finally` ПОСЛЕ `_ignore_signals()`
    # — то есть на замолчавшей машине прогон вставал намертво и Ctrl-C его уже
    # не брал, а журнал оставался недописанным.
    SHORT_CMD_S = 60.0

    def check_deadman(self, tries: int = 3, pause: float = 4.0) -> str:
        """Взведён ли дозор мертвеца НА САМОЙ машине.  Молчать здесь нельзя.

        Дозор — единственный из четырёх способов гашения, который не зависит
        ни от нашего процесса, ни от нашего ключа.  При пустом
        `CONTAINER_API_KEY` он оставался живым циклом, который раз в полминуты
        стучит `curl -X DELETE` с пустым Bearer: снаружи неотличимо от
        работающего, а на деле выключен, и узнали бы мы об этом только по
        счёту за забытую машину.  Проверить было НЕЧЕМ — ONSTART теперь пишет
        доклад в файл, а это его чтение.

        Три попытки с паузой, потому что доклад пишет фоновый цикл onstart:
        ssh обычно готов позже него, но полагаться на порядок нельзя, а ложная
        тревога учит не смотреть на тревоги вовсе.

        Возвращает строку доклада; она же уезжает в журнал прогона.
        """
        # Путь объявлен рядом с ONSTART, который этот файл и пишет: двух
        # экземпляров пути быть не должно.  Импорт внутри метода — чтобы
        # `box.py` не тянул пакет `vastai` ради одной строки.
        from .vast import DEADMAN_STATE
        state = ""
        for i in range(max(1, tries)):
            rc, out = self.run(f"cat {DEADMAN_STATE} 2>/dev/null", stream=False,
                               deadline=time.time() + self.SHORT_CMD_S)
            state = (out or "").strip()
            # `ARMED` латиницей — см. ONSTART: доклад проходит через API vast,
            # оболочку машины и ssh, и целость UTF-8 на этом пути непроверяема
            # без аренды.
            if rc == 0 and state.startswith("ARMED"):
                log(f"  дозор мертвеца взведён: {state}")
                self.deadman = state
                return state
            if i + 1 < max(1, tries):
                time.sleep(pause)
        self.deadman = state or "доклада нет"
        log(f"!!! ДОЗОР МЕРТВЕЦА НЕ ВЗВЕДЁН: {self.deadman}")
        log(f"!!! Машина {self.host}:{self.port} НЕ УБЬЁТ СЕБЯ САМА, если наш "
            f"процесс умрёт. Уничтожение держится только на нас: "
            f"finally, сигналы и сторож бюджета — все три в этом процессе.")
        return self.deadman

    def set_deadman(self, seconds: int) -> None:
        """Переставить срок дозора — например, перед --keep.

        Пишем во временный файл и переносим: `echo > файл` на оборванном ssh
        оставляет файл ПУСТЫМ, а пустое значение в дозоре разворачивается в
        `[ N -gt ]` — синтаксическую ошибку, то есть ложь, то есть машина не
        убьёт себя никогда.  `mv` в пределах файловой системы атомарен.

        Код возврата разбирается, а не глотается: вызывающий печатал «дозор
        переставлен» независимо от того, ответил ssh или вернул 255.
        """
        rc, out = self.run(
            f"echo {int(seconds)} > /root/.alive.grace.tmp && "
            f"mv /root/.alive.grace.tmp /root/.alive.grace", stream=False,
            deadline=time.time() + self.SHORT_CMD_S)
        if rc != 0:
            raise RuntimeError(
                f"дозор не переставлен (rc={rc}): {out.strip()[:200]}")

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
