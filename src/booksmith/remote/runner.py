"""Жизненный цикл прогона: снять машину, посчитать, забрать, уничтожить.

Уничтожение — самое важное здесь, поэтому оно продублировано трижды:
`finally` на любом выходе, перехват SIGINT/SIGTERM (иначе `finally` не
выполнится) и сторожевой поток по бюджету (на случай, если основной поток
залип в ssh, который не отвечает).
"""
import json
import os
import signal
import threading
import time

from . import ledger
from .box import Box
from .spec import JobSpec
from .vast import Vast, log


class Budget:
    """Жёсткий потолок: и по деньгам, и по времени.

    Дедлайн считается по цене конкретного оффера, а не по абстрактным минутам:
    $1.00 на карте за $0.34/час — это 2.9 часа, на карте за $2 — 30 минут.
    """

    def __init__(self, spec: JobSpec, dph: float, t0: float | None = None):
        self.started = time.time()
        # Время отсчитывается от начала ПРОГОНА (`t0`), а не от начала
        # попытки.  Прежде `Budget` заводился внутри цикла попыток, и каждая
        # отбракованная машина дарила прогону ещё один полный срок: четыре
        # попытки по 480 с сдвигали потолок на 32 минуты.  Деньги, наоборот,
        # считаются по ЭТОЙ машине — уничтоженная больше не берёт.
        self.t0 = self.started if t0 is None else t0
        self.eaten = self.started - self.t0
        by_money = spec.budget_usd / max(dph, 1e-6) * 3600
        by_time = spec.timeout_minutes * 60 - self.eaten
        # Отрицательный остаток — не «нулевой бюджет», а беда выше по течению:
        # мы уже сняли машину, на которую времени нет.  Молчать нельзя, иначе
        # сторож просто убьёт её и всё будет выглядеть как плохой рынок.
        if by_time <= 0:
            raise SystemExit(
                f"бюджет времени исчерпан ДО начала счёта: на попытки ушло "
                f"{self.eaten/60:.1f} мин при потолке "
                f"{spec.timeout_minutes:.0f} мин")
        self.seconds = min(by_money, by_time)
        self.dph = dph
        self.limited_by = "деньгам" if by_money < by_time else "времени"

    @property
    def deadline(self) -> float:
        return self.started + self.seconds

    @property
    def spent(self) -> float:
        return self.dph * (time.time() - self.started) / 3600

    def describe(self) -> str:
        # Число, а не «готово»: по съеденному на попытки видно, почему
        # потолок оказался короче объявленного.
        return (f"бюджет: ${self.dph:.3f}/час, потолок по {self.limited_by} — "
                f"{self.seconds/60:.0f} мин"
                + (f" (на попытки уже ушло {self.eaten/60:.0f} мин)"
                   if self.eaten >= 60 else ""))


def _watchdog(vast: Vast, get_iid, budget: Budget, done: threading.Event):
    """Убить инстанс по истечении бюджета, что бы ни делал основной поток.

    Тело обёрнуто целиком: исключение здесь убивало бы поток молча, а это
    последний рубеж — основной поток в этот момент может висеть в ssh.
    И одной попытки мало: если уничтожить не вышло, надо пробовать снова.
    """
    fired = False
    while not done.wait(15):
        try:
            if not fired and time.time() <= budget.deadline:
                continue
            iid = get_iid()
            if not iid:
                continue
            if not fired:
                log(f"!!! БЮДЖЕТ ИСЧЕРПАН (${budget.spent:.3f}) — уничтожаю {iid}")
                fired = True
            if vast.destroy(int(iid)):
                return
        except Exception as e:                     # noqa: BLE001 — рубеж падать не вправе
            log(f"  сторож: {type(e).__name__}: {e}")


class _Interrupted(Exception):
    pass


def _install_signals():
    """Ctrl-C и SIGTERM должны разворачиваться в исключение.

    Иначе процесс умрёт мимо `finally`, и инстанс останется работать.
    """
    def handler(signum, _frame):
        raise _Interrupted(f"сигнал {signum}")
    old = {}
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            old[s] = signal.signal(s, handler)
        except ValueError:
            pass                       # не главный поток — и не надо
    return old


def _restore_signals(old):
    for s, h in old.items():
        try:
            signal.signal(s, h)
        except ValueError:
            pass


def _ignore_signals():
    """Отключить обработчик на время уборки.

    Второй Ctrl-C — рефлекс, когда первый выглядит зависшим.  Раньше он
    прилетал прямо в `destroy` (пять попыток по 4с) и уносил процесс мимо
    уничтожения: инстанс оставался жив и продолжал биллиться.
    """
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, signal.SIG_IGN)
        except ValueError:
            pass


def _run_facts(outdir: str) -> dict:
    """Что задача сама сообщила о прогоне — в журнал, для подгонки модели.

    Раннер про OCR ничего не знает и знать не должен: он просто подбирает
    небольшие json-файлы, которые задача оставила в каталоге результата.
    """
    facts = {}
    for name in ("run.json", "vllm.json", "progress.json"):
        path = os.path.join(outdir, name)
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d, dict):
                facts.update(d)
        except Exception:
            pass
    return facts


def _warm(spec: JobSpec) -> list[int]:
    """Машины, где наш образ уже поднимался.

    Ценность не в кеше самого образа — он 54 МБ и едет секунды.  Ценность в
    том, что vast на свежей машине достраивает поверх него свой слой с ssh, а
    это индекс Debian и под сотню пакетов: шесть минут против тридцати
    четырёх секунд на машине, где эта достройка уже собрана.

    Я это предпочтение однажды выключил, решив, что при маленьком образе оно
    не нужно, — и ошибся: дорого не выкачивание образа, дорога достройка.
    """
    bad = set(ledger.bad_machines())
    # Порядок важен: сначала те, кого мы видели быстрыми, по возрастанию
    # времени счёта; потом остальные прогретые, свежие первыми.  Заявленная
    # скорость оффера — реклама, и по журналу она врёт втрое.
    fast = [m for m in ledger.fast_machines(spec.image, job=spec.name)
            if m not in bad]
    slow = set(ledger.slow_machines(spec.image, job=spec.name))
    warm = [m for m in ledger.warm_machines(spec.image)
            if m not in bad and m not in fast and m not in slow]
    # Число, а не молчание.  Отбраковка по времени работает только внутри
    # одной задачи, и у первого прогона новой книги истории нет — тогда `slow`
    # пуст не потому, что все машины хороши.  Прежде здесь стоял хардкод по
    # имени стенда, и он молча выбирал ноль записей ровно так же; разница в
    # том, что теперь это видно.
    log(f"предпочтение машин: быстрых {len(fast)}, прогретых {len(warm)}, "
        f"отбраковано медленных {len(slow)}"
        + ("" if slow else f" (истории по задаче «{spec.name}» нет — "
                           f"по времени не отбраковано ничего)"))
    return fast + warm


def connect(vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None,
            boot_limit: float = 2100, attempt_limit: float | None = None) -> Box:
    """Дождаться машины и ssh.  boot_limit — общий срок, а не только на запуск.

    Раньше он уходил только в wait_running, а wait_ready ждал по своему
    умолчанию в 420 с, плюс привязка ключа и зонды.  Одна негодная попытка
    стоила до десяти минут аренды, а лог при этом писал «не поднялась за
    2 мин».  Замер этого вечера: пять попыток съели пятнадцать минут.
    """
    t_end = time.time() + (attempt_limit or boot_limit)
    # Ожидание запуска тоже внутри общего срока.  Прежде сюда уходил
    # `boot_limit` целиком, и `attempt_limit` не ограничивал ничего: попытка,
    # объявленная восьмиминутной, могла простоять тридцать пять минут на уже
    # биллящейся машине.
    vast.wait_running(iid, timeout=max(30.0, min(boot_limit,
                                                 t_end - time.time())))
    # Привязка ключа сразу после создания инстанса — гонка: контейнера ещё
    # нет, и vast достраивает его своим слоем с ssh минуты по три.  Ключ,
    # привязанный до этого, до authorized_keys иногда не доезжает, и мы
    # получаем `Permission denied (publickey)` уже после того, как заплатили
    # за старт.  Повторяем, когда контейнер точно существует; привязка
    # идемпотентна, лишний вызов ничего не портит.
    if ssh_key:
        vast.attach_key(iid, ssh_key)
    user, host, port = vast.ssh_target(iid)
    log(f"ssh {user}@{host}:{port}")
    box = Box(user, host, port, ssh_key, spec.workdir)
    box.wait_ready(timeout=max(60.0, t_end - time.time()))
    # Пульс — сразу после ssh: с этого момента машина знает, что оператор
    # жив, и уничтожит себя сама, если он замолчит.  См. ONSTART в vast.py.
    box.start_heartbeat()
    return box


def execute(box: Box, spec: JobSpec, outdir: str,
            deadline: float | None = None) -> int:
    """Залить вход, посчитать, забрать выход.  Машина уже поднята."""
    rc, out = box.run(f"mkdir -p {spec.workdir} && echo ok", stream=False)
    if rc != 0:
        raise RuntimeError(f"не создаётся {spec.workdir}: {out}")

    log("заливаю входные файлы...")
    for local, remote_rel in spec.inputs.items():
        if not os.path.exists(local):
            raise SystemExit(f"нет файла: {local}")
        box.push(local, remote_rel)
        log(f"  {os.path.basename(local)} -> {remote_rel}")

    # На прогретой машине от прошлого прогона остаётся каталог с результатом,
    # и задача считает работу сделанной: возобновление видит 20 готовых страниц
    # и досчитывает одну.  Прогон при этом выглядит успешным и стоит денег.
    # Поэтому чистим — кроме случая, когда возобновление и задумано.
    if not spec.resume:
        # Со сроком и С ПРОВЕРКОЙ.  Незамеченная неудача здесь означает, что
        # результат прошлого прогона остался на месте, а `--resume` его
        # засчитает: прогон выглядит успешным, страницы чужие.
        rc, out = box.run(f"rm -rf {spec.workdir}/{spec.outputs}",
                          stream=False, deadline=deadline)
        if rc != 0:
            raise RuntimeError(
                f"не удалось очистить {spec.workdir}/{spec.outputs} "
                f"(rc={rc}): {out.strip()[:200]}")
    rc, out = box.run(f"mkdir -p {spec.workdir}/{spec.outputs}", stream=False,
                      deadline=deadline)
    if rc != 0:
        raise RuntimeError(f"не создаётся каталог результата (rc={rc}): "
                           f"{out.strip()[:200]}")
    box.start_sync(spec.outputs, outdir, exclude=spec.pull_exclude)
    try:
        log("запускаю задачу...")
        env = " ".join(f"{k}={v}" for k, v in spec.env.items())
        cmd = f"cd {spec.workdir} && {env} {spec.command}".strip()
        rc, _ = box.run(cmd, deadline=deadline)
    finally:
        box.stop_sync()
        # Сколько стоит каждое исключение — ДО того, как оно сработает, и
        # числом.  Прежде исключения стояли молча, и «экономия» в 0.8%
        # выгрузки, стоившая четырём книгам постраничной разметки, ни разу не
        # была названа вслух.  Замер вхолостую, ноль переданных байт.
        if spec.pull_exclude:
            try:
                box.weigh_exclude(spec.outputs, spec.pull_exclude, outdir)
            except Exception as e:
                log(f"  вес исключений не измерен ({e}) — выгрузка идёт как есть")
        log("забираю результат целиком...")
        if box.pull(spec.outputs, outdir,
                    exclude=spec.pull_exclude) != 0 and rc == 0:
            # Задача отработала, а результат не доехал — это не успех.
            # Раньше такой прогон возвращал 0, и оператор получал неполный
            # разбор как готовый; вместе с нечищенным каталогом это было
            # неотличимо от нормы.
            log("ВНИМАНИЕ: результат выкачался не полностью")
            rc = 75
    return rc


# Пять попыток, а не три: отбраковка теперь стоит около двух минут, а рынок
# бывает и таким, что три машины подряд оказываются негодными — так и вышло,
# все три из одного кластера в Нидерландах.
#
# Ниже этого машина непригодна: заявленные хостом мегабиты — про его
# собственный доступ в интернет, а не про путь до нас.  Замер: машина с
# обещанными 1188 Мбит/с приняла 3.5 МБ входного файла за семь с половиной
# минут, то есть 62 кбит/с.  Пятнадцать минут аренды ушли впустую.
#
# Порог низкий намеренно.  Один поток ssh даёт немного даже на здоровой
# машине — шифрование плюс окно потока на длинном маршруте: удачный прогон
# заливал те же 3.5 МБ за 4 секунды, это ~7 Мбит/с.  Первая версия порога
# стояла на 25 и отбраковала пять машин подряд, все годные.  Отделять надо
# не быстрых от медленных, а работающих от сломанных, а между ними два
# порядка: 7 Мбит/с против 0.06.
MIN_LINK_MBPS = 2.0

# Скорость машины «из мира» пока НЕ отбраковывает, а только пишется в
# журнал.  Первая версия зонда мерила один поток и дала обратную
# зависимость с реальным временем установки колёс; порог 150 при этом
# отбраковал пять машин подряд, весь доступный рынок.  Зонд переписан на
# несколько потоков, но ставить порог по двум точкам — та же ошибка, что
# уже была сделана дважды.  Ждём данных в журнале.
MIN_DOWNLOAD_MBPS = 0.0
MAX_ATTEMPTS = 5

# Сколько ждать контейнера, прежде чем взять другую машину.
#
# Две минуты — по журналу, а не на глаз: из тринадцати подъёмов одиннадцать
# уложились в две минуты при медиане 1.4.  Не уложились ровно две машины, и
# обе оказались негодными — одна из них та, что потом принимала входной файл
# со скоростью 62 кбит/с.
#
# Дольше бывает законно: наш образ на 54 МБ приезжает за секунды, но следом
# vast достраивает свой слой с ssh — индекс Debian и под сотню пакетов.
# Поэтому машина, брошенная по этому потолку, НЕ считается плохой навсегда:
# достройка на ней доберётся до конца и в следующий раз машина поднимется
# за полминуты.  В вечный список идут только те, у кого сломан канал.
BOOT_LIMIT_S = 120.0

# Общий потолок одной попытки: запуск контейнера ПЛЮС ssh.  Раньше в connect
# уходил только BOOT_LIMIT_S, а wait_ready ждал по своим 420 с, и негодная
# попытка стоила до десяти минут.  Но и сжать всё в 120 с нельзя: vast
# достраивает образ своим слоем ssh минуты по три, и такой срок отбраковывает
# годные машины — проверено, два прогона подряд не нашли ни одной из десяти.
# Пять минут оказались слишком жёсткими: vast числит контейнер запущенным
# раньше, чем ssh-демон начинает слушать, и «Connection refused» тянется
# минуты по четыре с половиной.  Две годные машины подряд были отбракованы.
# Раньше на ssh отводилось 420 с отдельно, то есть попытка могла идти до
# девяти минут; восемь — середина, которая не душит и не разоряет.
ATTEMPT_LIMIT_S = 480.0

# Срок дозора мертвеца при --keep: машина оставлена нарочно, но не навсегда.
# Четыре часа — столько, чтобы вернуться к прогретой машине в тот же вечер,
# и не столько, чтобы забытый инстанс проел бюджет за ночь.
KEEP_GRACE_S = 4 * 3600


def _our_downlink_mbps(timeout: float = 20.0, mb: int = 1) -> float:
    """Скорость НАШЕГО канала вниз, чтобы не винить в ней машины.

    Зонд канала меряет путь от машины к нам и потому упирается в нас же.
    Отличить «машина плохая» от «мы медленные» он не может, а порог стоял
    ровно на нашем потолке: вечером 20 августа наш канал просел до 2.3 Мбит,
    и две попытки аренды подряд по пять машин каждая были отбракованы —
    молча, и выглядело это как «плохой рынок».

    Ноль означает «не смогли измерить»; тогда порог остаётся прежним.
    """
    import urllib.request
    try:
        t0 = time.time()
        # Мегабайта достаточно и он укладывается даже в узкий канал: три
        # мегабайта на 2.3 Мбит/с не влезали в срок, и замер возвращал ноль —
        # то есть страховка от узкого канала сама им же и ломалась.
        # Заголовок обязателен: без него Cloudflare отвечает 403, замер
        # возвращает ноль, и страховка от узкого канала молча выключается.
        req = urllib.request.Request(
            f"https://speed.cloudflare.com/__down?bytes={mb * 1000000}",
            headers={"User-Agent": "booksmith/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            n = len(r.read())
        dt = max(time.time() - t0, 1e-6)
        return n * 8 / dt / 1e6
    except Exception:
        return 0.0


def _rent(vast: Vast, spec: JobSpec, ssh_key: str | None, state: dict,
          rec, guards: list, t0: float, undead: list | None = None):
    """Снять машину, дождаться ssh и проверить канал до неё.

    Плохая машина отсеивается здесь за двадцать секунд, а не через пятнадцать
    минут на заливке входных файлов.  У каждой попытки свой сторож: сторож от
    брошенной попытки нельзя оставлять живым, иначе он дождётся своего
    дедлайна и уничтожит уже следующую, чужую машину.
    """
    # Отбракованные машины исключаются навсегда, а не на один прогон: без
    # этого предпочтение прогретых ведёт обратно на ту же грабли.
    ours = _our_downlink_mbps()
    floor = MIN_LINK_MBPS
    if ours:
        # Машина не может отдать нам быстрее, чем мы принимаем.  Требовать с
        # неё больше половины нашего же канала — предел разумного.
        floor = min(MIN_LINK_MBPS, 0.5 * ours)
        log(f"наш канал вниз ≈ {ours:.1f} Мбит/с, "
            f"порог отбраковки машин {floor:.2f} Мбит/с")
        if ours < 2 * MIN_LINK_MBPS:
            log("ВНИМАНИЕ: наш канал узкий — выкачивание результата будет долгим")

    avoid: list[int] = list(ledger.bad_machines())
    undead = undead if undead is not None else []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Не снимать машину, на которую не осталось времени.  Внесено вместе
        # с отсчётом бюджета от `t0` и ловит его же изнанку: при коротком
        # `timeout_minutes` остаток уходил в минус, `Budget` отдавал дедлайн
        # В ПРОШЛОМ, и сторож уничтожал свежеснятую машину через 15 секунд.
        # Замер: timeout_minutes=30, попытки по 480 с — на пятой потолок
        # −2 мин.  Платить за машину, которую сами же убьём, хуже, чем
        # сказать вслух, что времени нет.
        left = spec.timeout_minutes * 60 - (time.time() - t0)
        if left <= ATTEMPT_LIMIT_S:
            raise SystemExit(
                f"на попытку не осталось времени: до потолка "
                f"{left/60:.1f} мин, а одна попытка берёт до "
                f"{ATTEMPT_LIMIT_S/60:.0f} мин "
                f"(попыток сделано {attempt - 1}). "
                f"Поднимите timeout_minutes или разберитесь, почему "
                f"машины отбраковываются.")
        offer = vast.pick(spec.host, spec.image_gb, spec.minutes, _warm(spec),
                          payload_gb=spec.payload_gb, warmup_s=spec.warmup_s,
                          avoid=avoid)
        dph = float(offer["dph_total"])
        rec.offer_id = int(offer["id"])
        rec.machine_id = offer.get("machine_id")
        rec.per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
        rec.inet_down_adv = float(offer.get("inet_down") or 0)
        rec.disk_bw = float(offer.get("disk_bw") or 0)
        rec.cpu_cores = float(offer.get("cpu_cores_effective") or 0)
        rec.cpu_ghz = float(offer.get("cpu_ghz") or 0)
        log(f"снимаю #{offer['id']} за ${dph:.3f}/час, диск {spec.host.disk_gb} ГБ"
            + (f" (попытка {attempt})" if attempt > 1 else ""))

        guard = threading.Event()
        guards.append(guard)
        budget = Budget(spec, dph, t0)
        # Своя ячейка на попытку, а не общий `state`.  Сторож брошенной
        # попытки переживает её намеренно — когда `destroy` не удался, ветка
        # ниже оставляет его добивать машину.  Но `state["iid"]` к тому
        # времени уже указывал на СЛЕДУЮЩУЮ машину, и, дождавшись своего
        # дедлайна, старый сторож уничтожал её посреди работы — ровно то, что
        # запрещает докстринг этой функции.
        #
        # `m=mine` не украшение: замыкание в цикле держит ПЕРЕМЕННУЮ, а не
        # значение, и без привязки по умолчанию все сторожа смотрели бы в
        # ячейку последней попытки — та же беда, только тише.
        mine: dict = {"iid": None}
        threading.Thread(target=_watchdog,
                         args=(vast, lambda m=mine: m["iid"], budget, guard),
                         daemon=True).start()

        def _remember(new_id: int, m=mine):
            state["iid"] = m["iid"] = new_id
            # Момент СОЗДАНИЯ удавшейся машины: от него, а не от начала
            # прогона, считается setup_s.
            state["t_create"] = time.time()
            rec.instance_id = new_id

        vast.create(int(offer["id"]), spec, on_created=_remember)
        if ssh_key:
            vast.attach_key(state["iid"], ssh_key)

        log(budget.describe())
        log("жду выкачивания образа и старта контейнера...")
        try:
            box = connect(vast, state["iid"], spec, ssh_key,
                          boot_limit=BOOT_LIMIT_S,
                          attempt_limit=ATTEMPT_LIMIT_S)
            link = box.probe()
            down = box.probe_download() if link >= MIN_LINK_MBPS else 0.0
            connect_failed = False
        except (RuntimeError, OSError) as e:
            connect_failed = True
            log(f"машина не дошла до ssh за {ATTEMPT_LIMIT_S/60:.0f} мин "
                f"({e}) — беру другую")
            link = down = 0.0
        rec.link_mbps = link
        rec.download_mbps = down
        if link >= floor and down >= MIN_DOWNLOAD_MBPS:
            log(f"канал: до нас {link:.0f}, из мира {down:.0f} Мбит/с")
            return box, dph, budget

        if not link and connect_failed:
            pass          # причина уже названа выше, второй раз незачем
        elif not link:
            # Ноль — это тайм-аут зонда, а не «неизвестно».  Раньше при нуле
            # обе ветки ниже были ложны, и машина уничтожалась молча: в
            # журнале ssh готов за 5 с, дальше пусто, а через полминуты
            # «УНИЧТОЖЕН». Пять таких подряд выглядели как «рынок плохой».
            log(f"зонд канала не уложился в срок (0 Мбит/с) — беру другую. "
                f"Если так подряд у всех машин, дело может быть в НАШЕМ "
                f"канале, а не в них")
        elif link < floor:
            log(f"канал до нас всего {link:.2f} Мбит/с "
                f"(нужно от {floor:.2f}) — беру другую")
            ledger.mark_bad(offer.get("machine_id"),
                            f"канал до нас {link:.2f} Мбит/с")
        elif link:
            log(f"машина тянет из мира всего {down:.0f} Мбит/с "
                f"(нужно от {MIN_DOWNLOAD_MBPS:.0f}) — беру другую")
        # Пульс надо остановить ДО того, как бросить машину: иначе наш же
        # поток продолжит её оживлять, и дозор мертвеца не сработает.
        try:
            box.stop_heartbeat()
        except Exception:
            pass
        # Результат уничтожения не выбрасываем: при неудаче машина жива, и
        # обнулять её id нельзя — блок finally её уже не тронет, а сторожа
        # мы бы погасили. Такой инстанс остаётся вообще без присмотра.
        if vast.destroy(int(state["iid"])):
            state["iid"] = mine["iid"] = None
            guard.set()
        else:
            log(f"инстанс {state['iid']} уничтожить не удалось — "
                f"оставляю сторожа и добью в конце")
            undead.append(int(state["iid"]))
        mid = offer.get("machine_id")
        if mid is not None:
            avoid.append(mid)

    raise RuntimeError(
        f"за {MAX_ATTEMPTS} попытки не нашлось машины с каналом от "
        f"{floor:.2f} Мбит/с"
        + (f"; наш собственный канал при этом {ours:.1f} Мбит/с — "
           f"возможно, дело в нём" if ours else ""))


def run_job(spec: JobSpec, outdir: str, ssh_key: str | None = None,
            keep: bool = False, reuse: int | None = None,
            dry_run: bool = False, report: dict | None = None,
            keep_until: float | None = None,
            keep_usd: float | None = None) -> int:
    """Полный прогон.  Возвращает код возврата задачи.

    `report` — необязательный словарь, куда кладётся `instance_id` снятой
    машины, её цена в час и потраченное.  Идентификатор нужен, чтобы второй и
    третий проходы попали на ту же машину; цена и трата — чтобы цепочка
    проходов знала, сколько бюджета осталось, и не заводила себе новый на
    каждом проходе.

    `keep_until` — АБСОЛЮТНЫЙ срок, до которого имеет смысл держать машину при
    `--keep`, и `keep_usd` — сколько денег осталось цепочке до этого прохода.
    Умолчание дозора — четыре часа, под «вернусь к прогретой машине вечером».
    Между проходами одной команды это слишком много: упади наш процесс в
    промежутке, карта биллится до утра.

    Именно абсолютный срок, а не длительность: первая редакция считала остаток
    в начале прохода, а ставила дозор в конце — то есть машина, начавшая
    последний проход с остатком в минуту, получала дозор на сто минут ПОСЛЕ
    его окончания.  И именно с деньгами: дозор, посчитанный из одних минут, на
    карте за $2/час превращал потолок в $1.00 в фактические девять.
    """
    vast = Vast()
    outdir = os.path.abspath(outdir)

    rec = ledger.Run(job=spec.name, image=spec.image, gpu=spec.host.gpu,
                     image_gb=spec.image_gb)
    old_signals = _install_signals()
    t0 = time.time()
    # id держим в изменяемой ячейке: сторож и блок уборки должны видеть его
    # сразу после создания инстанса, а не после возврата из create().
    state = {"iid": reuse}
    offer, done = None, threading.Event()

    if dry_run:
        if reuse:
            log(f"проверочный запуск: считал бы на инстансе {reuse}")
        else:
            warm = _warm(spec)
            offer = vast.pick(spec.host, spec.image_gb, spec.minutes, warm,
                              payload_gb=spec.payload_gb,
                              warmup_s=spec.warmup_s)
            log(f"проверочный запуск — снял бы #{offer['id']} "
                f"за ${float(offer['dph_total']):.3f}/час")
        _restore_signals(old_signals)
        return 0

    # Локальный каталог тоже надо чистить, а не только удалённый: rsync идёт
    # без --delete, и страницы прошлого прогона оставались лежать вперемешку
    # с новыми.  Хуже того, _run_facts подхватывал старые run.json и
    # progress.json и писал их в журнал как данные нового прогона — то есть
    # подделывались ещё и числа, по которым выбирается машина.
    if not spec.resume and os.path.isdir(outdir) and os.listdir(outdir):
        import shutil
        shutil.rmtree(outdir)
        log(f"локальный каталог {outdir} очищен от прошлого прогона")
    os.makedirs(outdir, exist_ok=True)
    guards: list[threading.Event] = []
    # Машины, которые пришлось бросить, но уничтожить не удалось: добиваем в
    # конце, иначе они биллятся до своего дозора мертвеца.
    undead: list[int] = []
    try:
        # Оставленная машина живёт не вечно: дозор мертвеца гасит её через
        # KEEP_GRACE_S.  Без этой проверки --reuse на погибший инстанс уходил
        # ждать его появления до boot_limit, то есть тридцать пять минут в
        # никуда, повторяя "статус=None".
        if reuse:
            try:
                gone = vast.instance(reuse) is None
            except Exception as exc:
                # Не смогли спросить — считаем, что машина жива.  Иначе мы
                # снимем вторую карту, а первая продолжит биллиться.
                log(f"не удалось проверить инстанс {reuse} ({exc}) — "
                    f"считаю, что он жив")
                gone = False
            if gone:
                log(f"инстанс {reuse} уже не существует — снимаю новую машину")
                reuse = None
                state["iid"] = None

        if reuse:
            log(f"переиспользую инстанс {reuse} — холодного старта нет")
            inst = vast.instance(reuse) or {}
            # Цену не выдумываем.  Прежде стояло `or 0.5`, и из выдуманного
            # числа строился ПОТОЛОК.  Замер при умолчаниях JobSpec
            # (budget_usd=1.00, timeout_minutes=90): карта за $2.00/час
            # получала 90 минут вместо 30 — втрое больше объявленного, и
            # только потому, что срок упирался в таймаут; без него было бы
            # вчетверо.  А `or` вдобавок глотал законный 0.0.  Ноль от
            # непонимания не должен молча становиться замером.
            raw_dph = inst.get("dph_total")
            if raw_dph is None:
                raise SystemExit(
                    f"инстанс {reuse} не сообщает цену (dph_total) — "
                    f"считать бюджет не из чего. Посмотрите: books ls")
            dph = float(raw_dph)
            rec.instance_id, rec.machine_id = reuse, inst.get("machine_id")
            budget = Budget(spec, dph, t0)
            guards.append(done)
            threading.Thread(target=_watchdog,
                             args=(vast, lambda: state["iid"], budget, done),
                             daemon=True).start()
            log(budget.describe())
            log("жду выкачивания образа и старта контейнера...")
            # Тот же потолок попытки, что и в ветке аренды.  Без него сюда
            # уходил `boot_limit` = 2100 с: тридцать пять минут ожидания на
            # машине, которая уже биллится.
            box = connect(vast, reuse, spec, ssh_key,
                          attempt_limit=ATTEMPT_LIMIT_S)
        else:
            box, dph, budget = _rent(vast, spec, ssh_key, state, rec,
                                     guards, t0, undead)

        rec.dph = dph
        # setup_s — от СОЗДАНИЯ удавшейся машины до готового ssh, как и
        # объявлено полем в журнале. Прежняя редакция мерила весь разбег
        # прогона: замер нашего канала, все отбракованные попытки, каждый
        # поиск предложений и оба зонда. Оценка `fit()` делила на это
        # постоянные 0.06 ГБ образа и печатала «эффективность канала 0.0052»
        # против константы 0.05 — расхождение в десять раз, целиком
        # арифметическое. Время на отбраковку теперь отдельным числом.
        t_create = state.get("t_create") or t0
        rec.setup_s = time.time() - t_create
        rec.reject_s = t_create - t0
        log(f"готово за {rec.setup_s/60:.1f} мин "
            f"(на отбраковку ушло {rec.reject_s/60:.1f} мин)")

        t1 = time.time()
        rc = execute(box, spec, outdir, deadline=budget.deadline)
        if rc != 0:
            # Смотрим в журнал vLLM: «CUDA unknown error» — это сломанная
            # карта на хосте, а не наша беда, и такая машина вернётся снова.
            # Канал у неё при этом хороший, так что зонд её пропускает.
            try:
                vl = os.path.join(outdir, "vllm.log")
                if os.path.exists(vl):
                    tail = open(vl, encoding="utf-8", errors="replace").read()
                    if "CUDA unknown error" in tail or "no CUDA-capable device" in tail:
                        ledger.mark_bad(rec.machine_id,
                                        "карта не инициализируется (CUDA)")
                        log(f"машина {rec.machine_id} записана в чёрный "
                            f"список: карта не инициализируется")
            except Exception:
                pass
        rec.run_s = time.time() - t1
        rec.extra.update(_run_facts(outdir))
        rec.ok = rc == 0
        if rc != 0:
            rec.note = f"задача вернула {rc}"
            log(f"задача завершилась с кодом {rc} — результат забран частично")
        return rc

    except _Interrupted as e:
        rec.note = f"прервано: {e}"
        log(f"прервано ({e}) — прибираю за собой")
        return 130
    except (Exception, SystemExit) as e:
        # SystemExit ловим НАРОЧНО.  Он BaseException, мимо `except Exception`
        # проходил насквозь, и авария — «нет офферов», «цены нет», «времени не
        # осталось» — уезжала в журнал с пустой пометкой и нулевой ценой, то
        # есть выглядела как бесплатный успех.  Ноль от непонимания.
        rec.note = f"{type(e).__name__}: {e}"
        raise
    finally:
        _ignore_signals()          # первым делом: уборку нельзя прерывать
        done.set()
        for g in guards:           # сторожа всех попыток, включая брошенные
            g.set()
        for dead in undead:
            if vast.destroy(int(dead)):
                log(f"брошенный инстанс {dead} добит")
            else:
                log(f"ВНИМАНИЕ: инстанс {dead} не уничтожен и продолжает "
                    f"биллиться — убейте вручную: books down {dead}")
        iid = state["iid"]
        elapsed = time.time() - t0
        rec.total_s = elapsed
        # Трафик считаем с полезной нагрузкой, а не с одним образом: колёса и
        # веса это 7.2 ГБ против 0.06, и без них цифра в журнале занижалась
        # примерно в сто раз.  Оценщик в pricing.py считает так же.
        rec.cost_usd = (rec.dph * elapsed / 3600
                        + rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024)
        # Пульс гасим ПЕРВЫМ делом уборки. Дозор мертвеца на самой карте —
        # единственный из четырёх способов гашения, который не ходит ни через
        # наш ключ, ни через наш процесс. Пока наш поток стучит `touch
        # /root/.alive` каждые 30 секунд, дозор выключен — и именно в тот
        # момент, когда остальные три уже сдались (сторожа погашены, повторы
        # destroy израсходованы), независимого способа не остаётся вовсе.
        # Вызов `stop_heartbeat` был во всём проекте ровно один, и не здесь.
        try:
            if box is not None:
                box.stop_heartbeat()
        except Exception as e:
            log(f"пульс не погашен: {e}")
        if iid and not keep:
            # Результат разбирается, как и везде.  Это был единственный
            # `destroy` во всём файле без проверки: пять неудачных попыток
            # печатали «НЕ СМОГ УНИЧТОЖИТЬ», а строкой ниже прогон рапортовал
            # «итого N мин» и возвращал 0 — при живой биллящейся машине.
            if not vast.destroy(int(iid)):
                log(f"ВНИМАНИЕ: инстанс {iid} НЕ УНИЧТОЖЕН и продолжает "
                    f"биллиться — убейте вручную: books down {iid}")
                rec.note = ((rec.note + "; ") if rec.note else "") + \
                    f"инстанс {iid} не уничтожен, ${rec.dph:.3f}/час"
        elif iid:
            # Оператор уходит нарочно, но дозор мертвеца на машине об этом не
            # знает и через свои 15 минут уничтожит инстанс.  Даём ему срок
            # побольше: --keep нужен, чтобы вернуться к машине следующим
            # прогоном, а не чтобы платить за неё сутками.
            if keep_until is None:
                grace = KEEP_GRACE_S
            else:
                left_s = keep_until - time.time()
                if keep_usd is not None:
                    left_usd = keep_usd - rec.cost_usd
                    left_s = min(left_s,
                                 left_usd / max(rec.dph, 1e-6) * 3600)
                # Десять минут на пересменку — столько, чтобы следующий проход
                # успел подключиться, и не столько, чтобы это стоило заметного.
                grace = max(300.0, left_s + 600)
            try:
                box.set_deadman(grace)
                log(f"дозор мертвеца на машине переставлен на "
                    f"{grace/60:.0f} мин без прогонов")
            except Exception as e:
                log(f"не смог переставить дозор мертвеца ({e}) — "
                    f"инстанс уничтожит себя через 15 минут")
            log(f"--keep: инстанс {iid} ОСТАВЛЕН И БИЛЛИТСЯ. "
                f"Следующий прогон: --reuse {iid}; убить: books down {iid}")
        if report is not None:
            report["instance_id"] = state["iid"]
            report["dph"] = rec.dph
            report["cost_usd"] = rec.cost_usd
        ledger.append(rec)
        log(f"итого {elapsed/60:.1f} мин ≈ ${rec.cost_usd:.3f}; "
            f"журнал: {ledger.LEDGER}")
        _restore_signals(old_signals)
