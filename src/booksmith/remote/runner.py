"""Жизненный цикл прогона: снять машину, посчитать, забрать, уничтожить.

Уничтожение — самое важное здесь, поэтому оно продублировано трижды:
`finally` на любом выходе, перехват SIGINT/SIGTERM (иначе `finally` не
выполнится) и сторожевой поток по бюджету (на случай, если основной поток
залип в ssh, который не отвечает).
"""
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


def _watchdog(vast: Vast, iid: int, budget: Budget, done: threading.Event):
    """Убить инстанс по истечении бюджета, что бы ни делал основной поток."""
    while not done.wait(15):
        if time.time() > budget.deadline:
            log(f"!!! БЮДЖЕТ ИСЧЕРПАН (${budget.spent:.3f}) — уничтожаю {iid}")
            vast.destroy(iid)
            return


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


def connect(vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None) -> Box:
    vast.wait_running(iid)
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
    iid, offer, box, done = reuse, None, None, threading.Event()

    if dry_run and not reuse:
        warm = ledger.warm_machines(spec.image)
        offer = vast.pick(spec.host, spec.image_gb, spec.minutes, warm)
        log(f"проверочный запуск — снял бы #{offer['id']} "
            f"за ${float(offer['dph_total']):.3f}/час")
        _restore_signals(old_signals)
        return 0

    os.makedirs(outdir, exist_ok=True)
    try:
        if reuse:
            log(f"переиспользую инстанс {reuse} — холодного старта нет")
            inst = vast.instance(reuse) or {}
            dph = float(inst.get("dph_total") or 0.5)
            rec.instance_id, rec.machine_id = reuse, inst.get("machine_id")
        else:
            warm = ledger.warm_machines(spec.image)
            offer = vast.pick(spec.host, spec.image_gb, spec.minutes, warm)
            dph = float(offer["dph_total"])
            rec.offer_id = int(offer["id"])
            rec.machine_id = offer.get("machine_id")
            rec.dph = dph
            rec.per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
            rec.inet_down_adv = float(offer.get("inet_down") or 0)
            rec.disk_bw = float(offer.get("disk_bw") or 0)
            log(f"снимаю #{offer['id']} за ${dph:.3f}/час, диск {spec.host.disk_gb} ГБ")
            iid = vast.create(int(offer["id"]), spec, ssh_key)
            rec.instance_id = iid

        budget = Budget(spec, dph)
        rec.dph = dph
        log(budget.describe())
        threading.Thread(target=_watchdog, args=(vast, iid, budget, done),
                         daemon=True).start()

        log("жду выкачивания образа и старта контейнера...")
        box = connect(vast, iid, spec, ssh_key)
        rec.setup_s = time.time() - t0
        mbps = rec.observed_mbps
        log(f"готово за {rec.setup_s/60:.1f} мин"
            + (f" (~{mbps:.0f} Мбит/с по образу)" if mbps else ""))

        t1 = time.time()
        rc = execute(box, spec, outdir, deadline=budget.deadline)
        rec.run_s = time.time() - t1
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
        done.set()
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
