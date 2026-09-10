"""Life cycle of a run: rent a machine, compute, fetch, destroy"""

import json
import os
import re
import shlex
import threading
import time
from . import ledger
from .box import Box
from fleet import job
from fleet import knobs
from .spec import JobSpec
from .vast import Vast
from fleet.log import log
from fleet.errors import Refusal


class Budget:
    def __init__(self, spec: JobSpec, dph: float, t0: float | None = None):
        self.started = time.time()
        self.t0 = self.started if t0 is None else t0
        self.eaten = self.started - self.t0
        by_money = spec.budget_usd / max(dph, 1e-06) * 3600
        by_time = spec.timeout_minutes * 60 - self.eaten
        if by_time <= 0:
            raise Refusal(
                f"the time budget is spent BEFORE the count begins: attempts ate {self.eaten / 60:.1f} min of a {spec.timeout_minutes:.0f} min ceiling"
            )
        self.seconds = min(by_money, by_time)
        self.dph = dph
        self.limited_by = "money" if by_money < by_time else "time"
        self.ceiling_usd = spec.host.max_dph * spec.timeout_minutes / 60
        self.money_unreachable = self.ceiling_usd <= spec.budget_usd

    @property
    def deadline(self) -> float:
        return self.started + self.seconds

    @property
    def spent(self) -> float:
        return self.dph * (time.time() - self.started) / 3600

    def describe(self) -> str:
        return (
            f"budget: ${self.dph:.3f}/hour, ceiling by {self.limited_by} -- {self.seconds / 60:.0f} min"
            + (f" (attempts already ate {self.eaten / 60:.0f} min)" if self.eaten >= 60 else "")
            + (
                f"; WARNING: budget_usd limits nothing -- without it a run still cannot pass ${self.ceiling_usd:.2f} (price cap x term), yet more is declared"
                if self.money_unreachable
                else ""
            )
        )


def _watchdog(vast: Vast, get_iid, budget: Budget, done: threading.Event):
    fired = False
    while not done.wait(15):
        try:
            if not fired and time.time() <= budget.deadline:
                continue
            iid = get_iid()
            if not iid:
                continue
            if not fired:
                log(f"!!! BUDGET SPENT (${budget.spent:.3f}) -- destroying {iid}")
                fired = True
            if vast.destroy(iid):
                return
        except Exception as e:
            log(f"  watchdog: {type(e).__name__}: {e}")


def _run_facts(outdir: str) -> dict:
    facts = {}
    for name in ("run.json", "vllm.json"):
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
    bad = set(ledger.bad_machines())
    fast = [m for m in ledger.fast_machines(spec.image, job=spec.name) if m not in bad]
    slow = set(ledger.slow_machines(spec.image, job=spec.name))
    warm = [
        m
        for m in ledger.warm_machines(spec.image)
        if m not in bad and m not in fast and (m not in slow)
    ]
    log(
        f"machine preference: {len(fast)} fast, {len(warm)} warm, {len(slow)} slow ones rejected"
        + ("" if slow else f" (no history for job '{spec.name}' -- nothing rejected by time)")
    )
    return fast + warm


def connect(
    vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None, attempt_limit: float = 480.0
) -> Box:
    t_end = time.time() + attempt_limit
    vast.wait_running(iid, timeout=max(30.0, t_end - time.time()))
    if ssh_key:
        vast.attach_key(iid, ssh_key)
    user, host, port = vast.ssh_target(iid)
    log(f"ssh {user}@{host}:{port}")
    box = Box(user, host, port, ssh_key, spec.workdir)
    box.wait_ready(timeout=max(60.0, t_end - time.time()))
    box.start_heartbeat()
    try:
        box.check_deadman()
    except BaseException:
        try:
            box.stop_heartbeat()
        except Exception as e:
            log(f"pulse not stopped after the link failed: {e}")
        raise
    return box


def execute(box: Box, spec: JobSpec, outdir: str, deadline: float | None = None) -> int:
    rc, out = box.run(f"mkdir -p {spec.workdir} && echo ok", stream=False)
    if rc != 0:
        raise RuntimeError(f"cannot create {spec.workdir}: {out}")
    log("uploading the input files...")
    for local, remote_rel in spec.inputs.items():
        if not os.path.exists(local):
            raise Refusal(f"no such file: {local}")
        box.push(local, remote_rel)
        log(f"  {os.path.basename(local)} -> {remote_rel}")
    if not spec.resume:
        rc, out = box.run(f"rm -rf {spec.workdir}/{spec.outputs}", stream=False, deadline=deadline)
        if rc != 0:
            raise RuntimeError(
                f"could not clear {spec.workdir}/{spec.outputs} (rc={rc}): {out.strip()[:200]}"
            )
    rc, out = box.run(f"mkdir -p {spec.workdir}/{spec.outputs}", stream=False, deadline=deadline)
    if rc != 0:
        raise RuntimeError(f"cannot create the result directory (rc={rc}): {out.strip()[:200]}")
    box.start_sync(spec.outputs, outdir, exclude=spec.pull_exclude)
    try:
        log("starting the job...")
        bad = [k for k in spec.env if not re.fullmatch("[A-Za-z_][A-Za-z0-9_]*", k)]
        if bad:
            raise Refusal(f"knob names unfit for a shell: {bad}")
        env = " ".join((f"{k}={shlex.quote(str(v))}" for k, v in spec.env.items()))
        cmd = f"cd {shlex.quote(spec.workdir)} && {env} {spec.command}".strip()
        rc, _ = box.run(cmd, deadline=deadline)
    finally:
        box.stop_sync()
        if spec.pull_exclude:
            try:
                box.weigh_exclude(spec.outputs, spec.pull_exclude, outdir)
            except Exception as e:
                log(f"  exclusions not weighed ({e}) -- fetching as is")
        log("fetching the whole result...")
        if box.pull(spec.outputs, outdir, exclude=spec.pull_exclude) != 0 and rc == 0:
            log("WARNING: the result did not arrive in full")
            rc = 75
    return rc


WITNESS_MBPS = 0.5


def _min_link_mbps() -> float:
    return knobs.number("MIN_LINK_MBPS")


MIN_DOWNLOAD_MBPS = 0.0
MAX_ATTEMPTS = 5
ATTEMPT_LIMIT_S = 480.0
KEEP_GRACE_S = 4 * 3600


def blame_machine(
    offer: dict,
    reason: str,
    *,
    ours: float,
    link: float,
    best_link: float,
    mark=None,
    say=None,
    ours_now: float | None = None,
) -> bool:
    mark = mark or ledger.mark_bad
    say = say or log
    if not ours:
        say(
            "  our channel is not measured -- NOT blacklisting: the probe's zero may have been ours"
        )
        return False
    if ours_now is not None and ours_now < 0.5 * ours:
        say(
            f"  NOT blacklisting: our own downlink has fallen from {ours:.1f} to {ours_now:.1f} Mbit/s since this rental began, so the machine that gave us {best_link:.2f} was measured on a different path than this one. The contrast is OURS"
        )
        return False
    if best_link < WITNESS_MBPS:
        say(
            f"  NOT blacklisting: the best any machine has given us over ssh is {best_link:.2f} Mbit/s, under the {WITNESS_MBPS:.1f} a witness must clear -- so nobody has shown this path works, and this one's {link:.2f} is as likely ours as its own. The list is forever and has no undo"
        )
        return False
    if best_link < 3 * link:
        say(
            f"  NOT blacklisting: the best ever given us over ssh is {best_link:.2f} Mbit/s against {link:.2f} here -- no witness against the machine, our own path looks narrow, and the list is forever"
        )
        return False
    try:
        mark(offer.get("machine_id"), reason)
    except Exception as e:
        say(
            f"  WARNING: machine {offer.get('machine_id')} could NOT be written to the blacklist ({e}) -- it will be offered again. The run goes on; the list is what failed, not the rental"
        )
        return False
    return True


def _our_downlink_mbps(timeout: float = 20.0, mb: int = 1) -> float:
    import urllib.request

    try:
        t0 = time.time()
        req = urllib.request.Request(
            f"https://speed.cloudflare.com/__down?bytes={mb * 1000000}",
            headers={"User-Agent": "fleet/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            n = len(r.read())
        dt = max(time.time() - t0, 1e-06)
        return n * 8 / dt / 1000000.0
    except Exception:
        return 0.0


def _rent(
    vast: Vast,
    spec: JobSpec,
    ssh_key: str | None,
    state: dict,
    rec,
    guards: list,
    t0: float,
    undead: list | None = None,
):
    ours = _our_downlink_mbps()
    limit = _min_link_mbps()
    floor = limit
    rec.our_downlink_mbps = ours or None
    if ours:
        floor = min(limit, 0.5 * ours)
        log(f"our downlink ~ {ours:.1f} Mbit/s, machine rejection floor {floor:.2f} Mbit/s")
        if ours < 2 * limit:
            log("WARNING: our channel is narrow -- the fetch will be slow")
    best_link = [0.0]

    def _blame(offer: dict, reason: str) -> None:
        blame_machine(
            offer,
            reason,
            ours=ours,
            link=link,
            best_link=best_link[0],
            ours_now=_our_downlink_mbps(),
        )

    avoid: list[int] = list(ledger.bad_machines())
    undead = undead if undead is not None else []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        job.current().check()
        left = spec.timeout_minutes * 60 - (time.time() - t0)
        if left <= ATTEMPT_LIMIT_S:
            raise Refusal(
                f"no time left for an attempt: {left / 60:.1f} min to the ceiling, one attempt takes up to {ATTEMPT_LIMIT_S / 60:.0f} min ({attempt - 1} made). Raise timeout_minutes, or find out why machines are rejected."
            )
        offer = vast.pick(
            spec.host,
            spec.image_gb,
            spec.minutes,
            _warm(spec),
            payload_gb=spec.payload_gb,
            warmup_s=spec.warmup_s,
            avoid=avoid,
        )
        dph = float(offer["dph_total"])
        rec.offer_id = int(offer["id"])
        rec.machine_id = offer.get("machine_id")
        rec.per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
        rec.inet_down_adv = float(offer.get("inet_down") or 0)
        rec.disk_bw = float(offer.get("disk_bw") or 0)
        rec.cpu_cores = float(offer.get("cpu_cores_effective") or 0)
        rec.cpu_ghz = float(offer.get("cpu_ghz") or 0)
        log(
            f"taking #{offer['id']} at ${dph:.3f}/hour, disk {spec.host.disk_gb} GB"
            + (f" (attempt {attempt})" if attempt > 1 else "")
        )
        guard = threading.Event()
        guards.append(guard)
        budget = Budget(spec, dph, t0)
        mine: dict = {"iid": None, "t_create": None}
        job.spawn(_watchdog, vast, lambda m=mine: m["iid"], budget, guard)

        def _remember(new_id: int, m=mine):
            state["iid"] = m["iid"] = new_id
            state["t_create"] = m["t_create"] = time.time()
            rec.instance_id = new_id

        def _charge(m=mine, price=dph):
            t = m.get("t_create")
            if t is None:
                return 0.0
            spent = price * (time.time() - t) / 3600
            rec.reject_usd += spent
            rec.reject_n += 1
            m["t_create"] = None
            log(
                f"  the rejected machine cost ${spent:.4f} ({(time.time() - t) / 60:.1f} min at ${price:.3f}/hour); rejections total ${rec.reject_usd:.4f} over {rec.reject_n} machines"
            )
            return spent

        try:
            vast.create(int(offer["id"]), spec, on_created=_remember)
        except Exception as e:
            log(
                f"offer #{offer['id']} not taken ({type(e).__name__}: {str(e)[:90]}) -- taking the next"
            )
            _charge()
            mid = offer.get("machine_id")
            if mid is None:
                log(f"  offer #{offer['id']} has no machine_id -- this machine can come again")
            else:
                avoid.append(int(mid))
            guard.set()
            continue
        if ssh_key:
            vast.attach_key(state["iid"], ssh_key)
        log(budget.describe())
        log("waiting for the image download and the container start...")
        try:
            box = connect(vast, state["iid"], spec, ssh_key, attempt_limit=ATTEMPT_LIMIT_S)
            link = box.probe()
            down = box.probe_download() if link >= floor else None
            connect_failed = False
        except (RuntimeError, OSError) as e:
            connect_failed = True
            log(
                f"machine did not reach ssh in {ATTEMPT_LIMIT_S / 60:.0f} min ({e}) -- taking another"
            )
            link, down = (0.0, None)
        best_link[0] = max(best_link[0], link)
        rec.link_mbps = link
        rec.download_mbps = down
        if link >= floor and (down is None or down >= MIN_DOWNLOAD_MBPS):
            log(
                f"channel: to us {link:.2f} Mbit/s, from the world "
                + (f"{down:.0f} Mbit/s" if down is not None else "not measured")
            )
            return (box, dph, budget)
        if not link and connect_failed:
            pass
        elif not link:
            log(
                "ZERO bytes to us in the time allowed -- taking another. This is the machine: the probe measures by time, so a live channel would give some number, however small"
            )
            _blame(offer, f"zero bytes to us in the time allowed (floor {floor:.2f} Mbit/s)")
        elif link < floor:
            log(
                f"channel to us only {link:.2f} Mbit/s (need {floor:.2f} or more) -- taking another"
            )
            _blame(offer, f"channel to us {link:.2f} Mbit/s")
        elif down is not None and down < MIN_DOWNLOAD_MBPS:
            log(
                f"machine pulls only {down:.0f} Mbit/s from the world (need {MIN_DOWNLOAD_MBPS:.0f} or more) -- taking another"
            )
        else:
            log(
                f"machine rejected and THE REASON WAS NOT NAMED: to us {link:.2f} Mbit/s against a floor of {floor:.2f}, from the world {(down if down is not None else 'not measured')} against {MIN_DOWNLOAD_MBPS}. This is a hole in the branches above, not a property of the machine"
            )
        try:
            box.stop_heartbeat()
        except Exception as e:
            log(
                f"WARNING: the abandoned machine's pulse still runs ({e}) -- our own thread may be holding its dead-man's watch off; check `books ls`"
            )
        if vast.destroy(state["iid"]):
            _charge()
            state["iid"] = mine["iid"] = None
            guard.set()
        else:
            log(
                f"instance {state['iid']} could not be destroyed -- leaving its watchdog and finishing it off at the end"
            )
            _charge()
            undead.append({"iid": int(state["iid"]), "dph": dph, "since": time.time()})
        mid = offer.get("machine_id")
        if mid is not None:
            avoid.append(int(mid))
    raise RuntimeError(
        f"in {MAX_ATTEMPTS} attempts no machine was found with a channel from {floor:.2f} Mbit/s"
        + (
            f"; our own channel was {ours:.1f} Mbit/s at the time -- it may be the cause"
            if ours
            else ""
        )
    )


def run_job(
    spec: JobSpec,
    outdir: str,
    ssh_key: str | None = None,
    keep: bool = False,
    reuse: int | None = None,
    dry_run: bool = False,
    report: dict | None = None,
    keep_until: float | None = None,
    keep_usd: float | None = None,
) -> int:
    vast = Vast()
    outdir = os.path.abspath(outdir)
    rec = ledger.Run(job=spec.name, image=spec.image, gpu=spec.host.gpu, image_gb=spec.image_gb)
    t0 = time.time()
    state = {"iid": reuse}
    offer, done = (None, threading.Event())
    if dry_run:
        if reuse:
            log(f"dry run: would compute on instance {reuse}")
        else:
            warm = _warm(spec)
            offer = vast.pick(
                spec.host,
                spec.image_gb,
                spec.minutes,
                warm,
                payload_gb=spec.payload_gb,
                warmup_s=spec.warmup_s,
            )
            log(f"dry run -- would take #{offer['id']} at ${float(offer['dph_total']):.3f}/hour")
        return 0
    if not spec.resume and os.path.isdir(outdir) and os.listdir(outdir):
        import shutil

        shutil.rmtree(outdir)
        log(f"local directory {outdir} cleared of the previous run")
    os.makedirs(outdir, exist_ok=True)
    for name in ("run.json", "vllm.json"):
        try:
            os.unlink(os.path.join(outdir, name))
        except FileNotFoundError:
            pass
    guards: list[threading.Event] = []
    undead: list[int] = []
    box = None
    try:
        if reuse:
            try:
                gone = vast.instance(reuse) is None
            except Exception as exc:
                log(f"could not check instance {reuse} ({exc}) -- taking it to be alive")
                gone = False
            if gone:
                log(f"instance {reuse} no longer exists -- taking a new one")
                reuse = None
                state["iid"] = None
        if reuse:
            log(f"reusing instance {reuse} -- no cold start")
            inst = vast.instance(reuse) or {}
            raw_dph = inst.get("dph_total")
            if raw_dph is None:
                raise Refusal(
                    f"instance {reuse} reports no price (dph_total) -- nothing to count a budget from. Look: books ls"
                )
            dph = float(raw_dph)
            rec.dph = dph
            rec.instance_id, rec.machine_id = (reuse, inst.get("machine_id"))
            budget = Budget(spec, dph, t0)
            guards.append(done)
            job.spawn(_watchdog, vast, lambda: state["iid"], budget, done)
            log(budget.describe())
            log("waiting for the image download and the container start...")
            box = connect(vast, reuse, spec, ssh_key, attempt_limit=ATTEMPT_LIMIT_S)
        else:
            box, dph, budget = _rent(vast, spec, ssh_key, state, rec, guards, t0, undead)
        rec.dph = dph
        rec.extra["deadman"] = box.deadman
        t_create = state.get("t_create") or t0
        rec.setup_s = time.time() - t_create
        rec.reject_s = t_create - t0
        log(f"ready in {rec.setup_s / 60:.1f} min ({rec.reject_s / 60:.1f} min went on rejections)")
        t1 = time.time()
        rc = execute(box, spec, outdir, deadline=budget.deadline)
        if rc != 0:
            try:
                vl = os.path.join(outdir, "vllm.log")
                if os.path.exists(vl):
                    tail = open(vl, encoding="utf-8", errors="replace").read()
                    if "CUDA unknown error" in tail or "no CUDA-capable device" in tail:
                        ledger.mark_bad(rec.machine_id, "the card does not initialise (CUDA)")
                        log(f"machine {rec.machine_id} blacklisted: the card does not initialise")
            except Exception as e:
                log(
                    f"WARNING: the CUDA check on machine {rec.machine_id} did not finish ({e}) -- if the card was dead, the machine was NOT blacklisted and will be offered again"
                )
        rec.run_s = time.time() - t1
        rec.extra.update(_run_facts(outdir))
        rec.ok = rc == 0
        if rc != 0:
            rec.note = f"the job returned {rc}"
            log(f"the job ended with code {rc} -- result fetched in part")
        return rc
    except (Exception, SystemExit) as e:
        rec.note = f"{type(e).__name__}: {e}"
        raise
    finally:
        done.set()
        for g in guards:
            g.set()
        for dead in undead:
            rec.reject_usd += dead["dph"] * (time.time() - dead["since"]) / 3600
            if vast.destroy(dead["iid"]):
                log(f"abandoned instance {dead['iid']} finished off")
            else:
                log(
                    f"WARNING: instance {dead['iid']} not destroyed and still billing -- kill it by hand: books down {dead['iid']}"
                )
        iid = state["iid"]
        elapsed = time.time() - t0
        rec.total_s = elapsed
        alive_s = time.time() - (state.get("t_create") or t0)
        rec.cost_usd = (
            rec.dph * alive_s / 3600
            + rec.reject_usd
            + rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024
        )
        try:
            if box is not None:
                box.stop_heartbeat()
        except Exception as e:
            log(f"pulse not stopped: {e}")
        if iid and (not keep):
            if not vast.destroy(iid):
                log(
                    f"WARNING: instance {iid} NOT DESTROYED and still billing -- kill it by hand: books down {iid}"
                )
                rec.note = (
                    rec.note + "; " if rec.note else ""
                ) + f"instance {iid} not destroyed, ${rec.dph:.3f}/hour"
        elif iid:
            if keep_until is None:
                grace = KEEP_GRACE_S
            else:
                left_s = keep_until - time.time()
                if keep_usd is not None:
                    left_usd = keep_usd - rec.cost_usd
                    left_s = min(left_s, left_usd / max(rec.dph, 1e-06) * 3600)
                grace = max(300.0, left_s + 600)
            try:
                box.set_deadman(grace)
                log(f"the machine's dead-man's watch reset to {grace / 60:.0f} min without a run")
            except Exception as e:
                log(
                    f"could not reset the dead-man's watch ({e}) -- the instance will destroy itself in 15 minutes"
                )
            log(
                f"--keep: instance {iid} LEFT ALIVE AND BILLING. Next run: --reuse {iid}; kill it: books down {iid}"
            )
        if report is not None:
            report["instance_id"] = iid if keep and iid else None
            report["dph"] = rec.dph
            report["cost_usd"] = rec.cost_usd
        try:
            ledger.append(rec)
        except Exception as e:
            log(
                f"WARNING: the run could NOT be written to the ledger ({e}) -- the money below is real and was not recorded. The run itself is finished; it is the record that failed"
            )
        log(
            f"total {elapsed / 60:.1f} min ~ ${rec.cost_usd:.3f} (rent {alive_s / 60:.1f} min at ${rec.dph:.3f}/hour = ${rec.dph * alive_s / 3600:.3f}"
            + (
                f"; {rec.reject_n} machines rejected for ${rec.reject_usd:.3f}"
                if rec.reject_n
                else ""
            )
            + f"; traffic ${rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024:.3f})"
            + f"; ledger: {ledger.file()}"
        )
