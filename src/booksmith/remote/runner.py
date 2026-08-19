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

    def __init__(self, spec: JobSpec, dph: float):
        by_money = spec.budget_usd / max(dph, 1e-6) * 3600
        by_time = spec.timeout_minutes * 60
        self.seconds = min(by_money, by_time)
        self.started = time.time()
        self.dph = dph
        self.limited_by = "деньгам" if by_money < by_time else "времени"

    @property
    def deadline(self) -> float:
        return self.started + self.seconds

    @property
    def spent(self) -> float:
        return self.dph * (time.time() - self.started) / 3600

    def describe(self) -> str:
        return (f"бюджет: ${self.dph:.3f}/час, потолок по {self.limited_by} — "
                f"{self.seconds/60:.0f} мин")


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
    return [m for m in ledger.warm_machines(spec.image) if m not in bad]


def connect(vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None,
            boot_limit: float = 2100) -> Box:
    vast.wait_running(iid, timeout=boot_limit)
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
    box.wait_ready()
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

    box.run(f"mkdir -p {spec.workdir}/{spec.outputs}", stream=False)
    box.start_sync(spec.outputs, outdir)
    try:
        log("запускаю задачу...")
        env = " ".join(f"{k}={v}" for k, v in spec.env.items())
        cmd = f"cd {spec.workdir} && {env} {spec.command}".strip()
        rc, _ = box.run(cmd, deadline=deadline)
    finally:
        box.stop_sync()
        log("забираю результат целиком...")
        box.pull(spec.outputs, outdir)
    return rc


# Пять попыток, а не три: отбраковка теперь стоит около двух минут, а рынок
# бывает и таким, что три машины подряд оказываются негодными — так и вышло,
# все три из одного кластера в Нидерландах.
#
# Ниже этого машина непригодна: заявленные хостом мегабиты — про его
# собственный доступ в интернет, а не про путь до нас.  Замер: машина с
# обещанными 1188 Мбит/с приняла 3.5 МБ входного файла за семь с половиной
# минут, то есть 62 кбит/с.  Пятнадцать минут аренды ушли впустую.
MIN_LINK_MBPS = 25.0
MAX_ATTEMPTS = 5

# Сколько ждать контейнера, прежде чем считать машину негодной.
#
# Порог щедрый не по доброте: наш образ на 54 МБ приезжает за секунды, но
# следом vast достраивает свой слой с ssh — качает индекс Debian на 8.8 МБ и
# под сотню пакетов (python3.11, dbus, packagekit).  Это втрое больше нашего
# образа и от нас не зависит.  Удачный прогон так поднимался 6.4 минуты, так
# что семь минут отсекали бы вполне рабочие машины.
BOOT_LIMIT_S = 480.0


def _rent(vast: Vast, spec: JobSpec, ssh_key: str | None, state: dict,
          rec, guards: list, t0: float):
    """Снять машину, дождаться ssh и проверить канал до неё.

    Плохая машина отсеивается здесь за двадцать секунд, а не через пятнадцать
    минут на заливке входных файлов.  У каждой попытки свой сторож: сторож от
    брошенной попытки нельзя оставлять живым, иначе он дождётся своего
    дедлайна и уничтожит уже следующую, чужую машину.
    """
    # Отбракованные машины исключаются навсегда, а не на один прогон: без
    # этого предпочтение прогретых ведёт обратно на ту же грабли.
    avoid: list[int] = list(ledger.bad_machines())
    for attempt in range(1, MAX_ATTEMPTS + 1):
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
        budget = Budget(spec, dph)
        threading.Thread(target=_watchdog,
                         args=(vast, lambda: state["iid"], budget, guard),
                         daemon=True).start()

        def _remember(new_id: int):
            state["iid"] = new_id
            rec.instance_id = new_id

        vast.create(int(offer["id"]), spec, on_created=_remember)
        if ssh_key:
            vast.attach_key(state["iid"], ssh_key)

        log(budget.describe())
        log("жду выкачивания образа и старта контейнера...")
        try:
            box = connect(vast, state["iid"], spec, ssh_key,
                          boot_limit=BOOT_LIMIT_S)
            link = box.probe()
        except (RuntimeError, OSError) as e:
            log(f"машина не поднялась ({e}) — беру другую")
            ledger.mark_bad(offer.get("machine_id"), f"не поднялась: {e}")
            link = 0.0
        rec.link_mbps = link
        if link >= MIN_LINK_MBPS:
            log(f"канал до машины: {link:.0f} Мбит/с")
            return box, dph, budget

        if link:
            log(f"канал до машины всего {link:.0f} Мбит/с "
                f"(нужно от {MIN_LINK_MBPS:.0f}) — беру другую")
            ledger.mark_bad(offer.get("machine_id"), f"канал {link:.0f} Мбит/с")
        vast.destroy(int(state["iid"]))
        state["iid"] = None
        guard.set()
        avoid.append(offer.get("machine_id"))

    raise RuntimeError(f"за {MAX_ATTEMPTS} попытки не нашлось машины "
                       f"с каналом от {MIN_LINK_MBPS:.0f} Мбит/с")


def run_job(spec: JobSpec, outdir: str, ssh_key: str | None = None,
            keep: bool = False, reuse: int | None = None,
            dry_run: bool = False) -> int:
    """Полный прогон.  Возвращает код возврата задачи."""
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

    os.makedirs(outdir, exist_ok=True)
    guards: list[threading.Event] = []
    try:
        if reuse:
            log(f"переиспользую инстанс {reuse} — холодного старта нет")
            inst = vast.instance(reuse) or {}
            dph = float(inst.get("dph_total") or 0.5)
            rec.instance_id, rec.machine_id = reuse, inst.get("machine_id")
            budget = Budget(spec, dph)
            guards.append(done)
            threading.Thread(target=_watchdog,
                             args=(vast, lambda: state["iid"], budget, done),
                             daemon=True).start()
            log(budget.describe())
            log("жду выкачивания образа и старта контейнера...")
            box = connect(vast, reuse, spec, ssh_key)
        else:
            box, dph, budget = _rent(vast, spec, ssh_key, state, rec,
                                     guards, t0)

        rec.dph = dph
        rec.setup_s = time.time() - t0
        log(f"готово за {rec.setup_s/60:.1f} мин")

        t1 = time.time()
        rc = execute(box, spec, outdir, deadline=budget.deadline)
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
    except Exception as e:
        rec.note = f"{type(e).__name__}: {e}"
        raise
    finally:
        _ignore_signals()          # первым делом: уборку нельзя прерывать
        done.set()
        for g in guards:           # сторожа всех попыток, включая брошенные
            g.set()
        iid = state["iid"]
        elapsed = time.time() - t0
        rec.total_s = elapsed
        rec.cost_usd = rec.dph * elapsed / 3600 + rec.per_tb * spec.image_gb / 1024
        if iid and not keep:
            vast.destroy(int(iid))
        elif iid:
            log(f"--keep: инстанс {iid} ОСТАВЛЕН И БИЛЛИТСЯ. "
                f"Следующий прогон: --reuse {iid}; убить: books remote down {iid}")
        ledger.append(rec)
        log(f"итого {elapsed/60:.1f} мин ≈ ${rec.cost_usd:.3f}; "
            f"журнал: {ledger.LEDGER}")
        _restore_signals(old_signals)
