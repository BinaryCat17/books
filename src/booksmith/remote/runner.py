"""Life cycle of a run: rent a machine, compute, fetch, destroy.

Destroying is the important part here, so it is done three ways over: `finally`
on any exit, SIGINT/SIGTERM caught (without which `finally` never runs), and a
watchdog thread on the budget (for when the main thread hangs in an ssh that
does not answer).
"""
import json
import os
import re
import shlex
import signal
import threading
import time

from . import ledger
from .box import Box
from ..run import knobs
from .spec import JobSpec
from .vast import Vast, log


class Budget:
    """A hard ceiling, on money and on time both.

    The deadline follows the price of THIS offer, not abstract minutes: $1.00
    on a $0.34/hour card is 2.9 hours, on a $2 card 30 minutes.
    """

    def __init__(self, spec: JobSpec, dph: float, t0: float | None = None):
        self.started = time.time()
        # Time runs from the start of the RUN (`t0`), not of the attempt.
        # Built inside the attempt loop, `Budget` gave every rejected machine
        # another full term: four attempts of 480 s pushed the ceiling out by
        # 32 minutes. Money counts THIS machine: a destroyed one bills no more.
        self.t0 = self.started if t0 is None else t0
        self.eaten = self.started - self.t0
        by_money = spec.budget_usd / max(dph, 1e-6) * 3600
        by_time = spec.timeout_minutes * 60 - self.eaten
        # A negative remainder is trouble upstream, not "zero budget": the
        # machine is already rented. Silence lets the watchdog kill it, and the
        # whole thing looks like a bad market.
        if by_time <= 0:
            raise SystemExit(
                f"the time budget is spent BEFORE the count begins: "
                f"attempts ate {self.eaten/60:.1f} min of a "
                f"{spec.timeout_minutes:.0f} min ceiling")
        self.seconds = min(by_money, by_time)
        self.dph = dph
        self.limited_by = "money" if by_money < by_time else "time"
        # A KNOB THAT LIMITS NOTHING IS WORSE THAN A MISSING ONE. A run cannot
        # cost more than `max_dph * timeout_minutes` by construction: at the
        # defaults $0.60/hour x 1.5 h = $0.90 against the declared $1.00, so
        # `budget_usd` NEVER fires and `limited_by` prints "time" on any
        # market. Not fixed -- the price cap and the term are the real defence
        # -- but said aloud, so nobody thinks the budget protects him. The gap
        # is wider still: `Budget` counts ONE machine, while rejected ones cost
        # money (`rec.reject_usd`) outside it.
        self.ceiling_usd = spec.host.max_dph * spec.timeout_minutes / 60
        self.money_unreachable = self.ceiling_usd <= spec.budget_usd

    @property
    def deadline(self) -> float:
        return self.started + self.seconds

    @property
    def spent(self) -> float:
        return self.dph * (time.time() - self.started) / 3600

    def describe(self) -> str:
        # A number, not "done": what the attempts ate shows why the ceiling
        # came out shorter than declared.
        return (f"budget: ${self.dph:.3f}/hour, ceiling by "
                f"{self.limited_by} -- {self.seconds/60:.0f} min"
                + (f" (attempts already ate {self.eaten/60:.0f} min)"
                   if self.eaten >= 60 else "")
                + (f"; WARNING: budget_usd limits nothing -- without it a "
                   f"run still cannot pass ${self.ceiling_usd:.2f} "
                   f"(price cap x term), yet more is declared"
                   if self.money_unreachable else ""))


def _watchdog(vast: Vast, get_iid, budget: Budget, done: threading.Event):
    """Kill the instance once the budget is out, whatever the main thread does.

    The body is wrapped whole: an exception here would kill the thread in
    silence, and this is the last line of defence -- the main thread may be
    hanging in ssh. One try is not enough either: if destroying failed, repeat.
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
                log(f"!!! BUDGET SPENT (${budget.spent:.3f}) -- "
                    f"destroying {iid}")
                fired = True
            if vast.destroy(int(iid)):
                return
        except Exception as e:                     # noqa: BLE001 -- a last line may not fall
            log(f"  watchdog: {type(e).__name__}: {e}")


class _Interrupted(Exception):
    pass


def _install_signals():
    """Ctrl-C and SIGTERM must unfold into an exception.

    Otherwise the process dies past `finally` and the instance keeps running.
    """
    def handler(signum, _frame):
        raise _Interrupted(f"signal {signum}")
    old = {}
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            old[s] = signal.signal(s, handler)
        except ValueError:
            pass                       # not the main thread -- no need
    return old


def _restore_signals(old):
    for s, h in old.items():
        try:
            signal.signal(s, h)
        except ValueError:
            pass


def _ignore_signals():
    """Turn the handler off for the duration of the cleanup.

    A second Ctrl-C is a reflex once the first looks hung. It used to land
    straight in `destroy` (five tries of 4 s) and carry the process past the
    destruction: the instance stayed alive and kept billing.
    """
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, signal.SIG_IGN)
        except ValueError:
            pass


def _run_facts(outdir: str) -> dict:
    """What the job itself reported about the run -- into the ledger, to tune
    the model.

    The runner knows nothing about OCR and must not: it just picks up the small
    json files the job left in the result directory.
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
    """Machines where our image has already come up.

    The value is not the image cache -- 54 MB, seconds. It is that on a fresh
    machine vast builds its own ssh layer on top, a Debian index and near a
    hundred packages: six minutes against thirty-four seconds where that build
    is already done. I once switched this preference off, reasoning that a
    small image made it pointless, and was wrong: the download is cheap, the
    build-up is not.
    """
    bad = set(ledger.bad_machines())
    # Order matters: the fast first by ascending compute time, then the rest of
    # the warm ones, freshest first. An offer's advertised speed is
    # advertising: by the ledger it lies threefold.
    fast = [m for m in ledger.fast_machines(spec.image, job=spec.name)
            if m not in bad]
    slow = set(ledger.slow_machines(spec.image, job=spec.name))
    warm = [m for m in ledger.warm_machines(spec.image)
            if m not in bad and m not in fast and m not in slow]
    # A number, not silence. Rejection by time works only within one job, and a
    # new book's first run has no history -- `slow` is then empty for a reason
    # other than every machine being good. A hardcoded bench name used to pick
    # zero records just as silently; now it shows.
    log(f"machine preference: {len(fast)} fast, {len(warm)} warm, "
        f"{len(slow)} slow ones rejected"
        + ("" if slow else f" (no history for job '{spec.name}' -- "
                           f"nothing rejected by time)"))
    return fast + warm


def connect(vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None,
            attempt_limit: float = 480.0) -> Box:
    """Wait for the machine and for ssh. ONE term for the whole attempt.

    It used to go to wait_running alone while wait_ready waited its own default
    of 420 s, plus the key attach and the probes: one bad attempt cost up to
    ten minutes of rental while the log said "did not come up in 2 min".
    Five attempts ate fifteen minutes that evening.

    A SECOND CEILING INSIDE THE FIRST IS GONE, and here is what it cost.
    `boot_limit` cut the container boot to `min(120, 480)` = 120 s, against the
    warning at `ATTEMPT_LIMIT_S` that vast builds its ssh layer for some three
    minutes. Paid run of 3 September 2026: machine 49873851 was pulling the
    image fine ("Download complete", "Pull complete") and was cut off at 2:12
    with 360 s of the attempt budget unspent. `t_end` bounds the attempt
    anyway; the inner ceiling defended nothing and rejected the good.
    """
    t_end = time.time() + attempt_limit
    # The boot wait is INSIDE the common term and has no ceiling of its own
    # (what one cost is above). The thirty-second floor is needed: without it
    # an attempt begun at the end of the term could not even ask for status.
    vast.wait_running(iid, timeout=max(30.0, t_end - time.time()))
    # Attaching the key straight after creating the instance is a race: the
    # container is not there yet, and a key attached before it sometimes never
    # reaches authorized_keys -- `Permission denied (publickey)` after we have
    # paid for the start. Repeat once the container exists; attaching is
    # idempotent.
    if ssh_key:
        vast.attach_key(iid, ssh_key)
    user, host, port = vast.ssh_target(iid)
    log(f"ssh {user}@{host}:{port}")
    box = Box(user, host, port, ssh_key, spec.workdir)
    box.wait_ready(timeout=max(60.0, t_end - time.time()))
    # The pulse right after ssh: from now on the machine destroys itself if the
    # operator falls silent (ONSTART in vast.py).
    box.start_heartbeat()
    # WHOEVER STARTED THE PULSE STOPS IT IF THINGS GO WRONG. Everything below
    # goes to the network, and `box` reaches the caller only at `return`: its
    # variable in `_rent` stays UNBOUND, or holds the PREVIOUS attempt's
    # machine. Reproduced with a stub `connect`: `_rent` catches the failure,
    # calls `box.stop_heartbeat()`, gets `UnboundLocalError`, swallows it in
    # `except Exception: pass`, and the machine leaves for `undead` WITH A LIVE
    # PULSE -- our thread knocks `touch /root/.alive` every 30 seconds to the
    # end of the run, DISABLING the dead-man's watch on exactly the abandoned
    # machine, the one kill path of four that needs neither our key nor our
    # process. On a second attempt it stops the previous machine's pulse
    # instead: twice as bad.
    try:
        # And at once: is the one this pulse is addressed to armed? One short
        # command over the already multiplexed connection, BEFORE anything is
        # uploaded -- a missing last line of defence must be learnt in the
        # first minute of rental, not from the bill.
        box.check_deadman()
    except BaseException:
        # `BaseException`, not `Exception`: on Ctrl-C the pulse must fall
        # silent too, else an interrupted run leaves the machine immortal.
        try:
            box.stop_heartbeat()
        except Exception as e:                                  # noqa: BLE001
            log(f"pulse not stopped after the link failed: {e}")
        raise
    return box


def execute(box: Box, spec: JobSpec, outdir: str,
            deadline: float | None = None) -> int:
    """Upload the input, compute, fetch the output. The machine is up already."""
    rc, out = box.run(f"mkdir -p {spec.workdir} && echo ok", stream=False)
    if rc != 0:
        raise RuntimeError(f"cannot create {spec.workdir}: {out}")

    log("uploading the input files...")
    for local, remote_rel in spec.inputs.items():
        if not os.path.exists(local):
            raise SystemExit(f"no such file: {local}")
        box.push(local, remote_rel)
        log(f"  {os.path.basename(local)} -> {remote_rel}")

    # A warm machine still holds the last run's result directory and the job
    # counts the work done: resume sees 20 finished pages and computes one, and
    # the run looks successful and costs money.
    if not spec.resume:
        # With a term and WITH A CHECK: an unnoticed failure leaves the last
        # run's result in place for `--resume` to count as this run's.
        rc, out = box.run(f"rm -rf {spec.workdir}/{spec.outputs}",
                          stream=False, deadline=deadline)
        if rc != 0:
            raise RuntimeError(
                f"could not clear {spec.workdir}/{spec.outputs} "
                f"(rc={rc}): {out.strip()[:200]}")
    rc, out = box.run(f"mkdir -p {spec.workdir}/{spec.outputs}", stream=False,
                      deadline=deadline)
    if rc != 0:
        raise RuntimeError(f"cannot create the result directory (rc={rc}): "
                           f"{out.strip()[:200]}")
    box.start_sync(spec.outputs, outdir, exclude=spec.pull_exclude)
    try:
        log("starting the job...")
        # Knob values are SHELL-QUOTED. The string is built for a foreign shell
        # out of `knobs.passthrough()`, i.e. the operator's environment: a
        # value with a space tore the command in two, one with `;` or `$(...)`
        # would run on the rented machine as code. The NAME is not quoted -- it
        # must be a legal shell variable name, and refusing HERE, before the
        # money, beats a syntax error after vLLM is up.
        bad = [k for k in spec.env if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)]
        if bad:
            raise SystemExit(f"knob names unfit for a shell: {bad}")
        env = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in spec.env.items())
        cmd = f"cd {shlex.quote(spec.workdir)} && {env} {spec.command}".strip()
        rc, _ = box.run(cmd, deadline=deadline)
    finally:
        box.stop_sync()
        # What each exclusion costs, BEFORE it fires and as a number. Silent
        # exclusions once "saved" 0.8% of the download and cost four books
        # their per-page markup. Measured dry, zero bytes transferred.
        if spec.pull_exclude:
            try:
                box.weigh_exclude(spec.outputs, spec.pull_exclude, outdir)
            except Exception as e:
                log(f"  exclusions not weighed ({e}) -- fetching as is")
        log("fetching the whole result...")
        if box.pull(spec.outputs, outdir,
                    exclude=spec.pull_exclude) != 0 and rc == 0:
            # The job finished and the result did not arrive -- no success.
            # Such a run used to return 0 and hand the operator an incomplete
            # parse as a finished one, indistinguishable from normal.
            log("WARNING: the result did not arrive in full")
            rc = 75
    return rc


# Five attempts, not three: a rejection now costs about two minutes, and the
# market can be such that three machines in a row are unusable -- which
# happened, all three from one cluster in the Netherlands.
#
# Below this floor a machine is unusable: a host's advertised megabits are
# about its own internet access, not the path to us. Measured: a machine
# promising 1188 Mbit/s took a 3.5 MB input file in seven and a half minutes,
# i.e. 62 kbit/s, and fifteen minutes of rental went to waste.
#
# The floor is deliberately low. One ssh stream gives little even on a healthy
# machine -- encryption plus the stream window on a long route: a good run
# pushed the same 3.5 MB in 4 seconds, some 7 Mbit/s. The first threshold stood
# at 25 and rejected five good machines in a row. Separate not fast from slow
# but working from broken: between them lie two orders, 7 Mbit/s against 0.06.
# DECLARED IN THE REGISTRY. As a module constant it cost this: at our
# 4.7 Mbit/s the floor computes as `min(2.0, 0.5*ours)` = 2.0 while the market
# gave 1.9 -- five rentals in a row rejected entirely, with no way to loosen it
# deliberately. And it missed the snapshot: renting at one threshold and
# refusing at another looked the same.
def _min_link_mbps() -> float:
    return float(knobs.knob("MIN_LINK_MBPS"))



# Speed "from the world" does NOT reject yet, it only goes to the ledger. The
# first probe measured one stream and gave an inverse relation to the real
# wheel-install time; a threshold of 150 then rejected five machines in a row,
# the whole available market. The probe now uses several streams, but setting a
# threshold off two points is the mistake already made twice.
#
# THE WAIT STARTS OVER. Everything in the ledger was measured by a probe asking
# six 12 MiB chunks of a 20.2 MB file: TWO streams of six downloaded, the other
# four got 416 and zero bytes (`box.probe_download`). Old numbers are
# incomparable with new -- do not set a threshold from them.
#
# AT 0.0 THIS REJECTS NOTHING, and that is the current state: no run has ever
# been refused for its downlink from the world. Kept as a named constant
# because the quantity IS measured and does reach the ledger; raise it and the
# branch below starts firing, which is why that branch is now the negation of
# the acceptance test rather than a catch-all.
MIN_DOWNLOAD_MBPS = 0.0
MAX_ATTEMPTS = 5

# How long to wait for a container before taking another machine.
#
# Two minutes by the ledger, not by eye: of thirteen boots eleven fitted into
# two minutes at a median of 1.4. Exactly two did not, and both machines proved
# unusable -- one of them the 62 kbit/s one.
#
# Longer is legitimate: the 54 MB image arrives in seconds, but vast then
# builds its ssh layer on top (see `_warm`). So a machine abandoned on this
# ceiling is NOT bad forever -- the build-up finishes and next time it comes up
# in half a minute. Only a broken channel earns the permanent list.
# `BOOT_LIMIT_S` IS GONE, not marked as debt: it rejected machines that were
# pulling the image fine (see `connect`).

# The ceiling of one attempt: container start PLUS ssh. 120 s is impossible --
# vast builds its ssh layer for some three minutes, and two runs in a row then
# found none of ten machines. Five minutes proved too harsh too: vast counts
# the container started before sshd listens, and "Connection refused" drags on
# for some four and a half minutes -- two good machines in a row rejected.
# Earlier ssh had its own 420 s, so an attempt could run nine minutes; eight is
# the middle that neither strangles nor ruins.
ATTEMPT_LIMIT_S = 480.0

# The dead-man's term under --keep: the machine is left on purpose, but not
# forever. Four hours -- enough to come back to a warm machine the same
# evening, not enough for a forgotten instance to eat the budget overnight.
KEEP_GRACE_S = 4 * 3600


def blame_machine(offer: dict, reason: str, *, ours: float, link: float,
                  best_link: float, mark=None, say=None) -> bool:
    """Onto the PERMANENT blacklist -- but only when the MACHINE is at fault.

    AT MODULE LEVEL, NOT A CLOSURE INSIDE `_rent`, and not for tidiness: a
    guard locked in a closure can neither be called from a check nor spoilt by
    a mutation -- the battery declared it checked while pulling its body out by
    parsing the source, i.e. it checked TEXT, not behaviour.

    The probe measures the path FROM the machine TO us and runs into us. On the
    evening of 20 August our channel sagged to 2.3 Mbit/s and two rentals in a
    row, five machines each, were rejected entirely -- good machines. On the
    PERMANENT list they would have ended the market for good, with the cause
    still at our end.

    THE RULE WAS `ours < 2 * limit`, AND IT WAS WRONG TWICE. First, `ours` is
    an HTTPS download from Cloudflare while the probe is A SINGLE SSH STREAM,
    and our gap between the transports is tenfold: 3 September 2026, HTTP 4.6
    and 2.4 Mbit/s against ssh 0.34 and 0.25 from two DIFFERENT machines in a
    row -- our own path, not coincidence, and both were blacklisted for nothing
    and taken off by hand. Second, the comparison was tied to `limit`, THE SAME
    KNOB that sets rejection: loosening the floor to let machines through made
    a permanent ban EASIER. One knob pulling two ways, and only paying showed
    it.

    Hence the instrument's own hint, carried through: "if it happens to every
    machine in a row, it may be OUR channel". Blame the machine only with a
    WITNESS: another machine that gave us three times more over the same ssh.

    AND A WITNESS OF ZERO IS NOT A WITNESS. `best_link < 3 * link` was the
    whole test, and at `link == 0.0` it reads `0.0 < 0.0` -- False -- so the
    machine went onto the permanent list with nothing to compare it against.
    That is the case the probe returns most often when OUR path is dead: the
    probe measures by time, so a broken path at our end gives zero from every
    machine, and every one of them would have been banned forever on the first
    attempt. The 3 September incident, arriving down the other branch.

    So the two silences are named apart, as everywhere else in this project:
    "nobody has ever given us anything over ssh" is not "the best we have seen
    is not three times this one".
    """
    mark = mark or ledger.mark_bad
    say = say or log
    if not ours:
        say("  our channel is not measured -- NOT blacklisting: the "
            "probe's zero may have been ours")
        return False
    if best_link <= 0:
        say(f"  NOT blacklisting: NO machine has yet given us anything over "
            f"ssh, so this one's {link:.2f} Mbit/s has no witness at all. "
            f"This is not 'the machine is the worst we have seen', it is "
            f"'we have seen nothing', and the list is forever")
        return False
    if best_link < 3 * link:
        say(f"  NOT blacklisting: the best ever given us over ssh is "
            f"{best_link:.2f} Mbit/s against {link:.2f} here -- no "
            f"witness against the machine, our own path looks narrow, "
            f"and the list is forever")
        return False
    mark(offer.get("machine_id"), reason)
    return True


def _our_downlink_mbps(timeout: float = 20.0, mb: int = 1) -> float:
    """The speed of OUR own downlink, so machines are not blamed for it.

    The channel probe measures the path from the machine to us and runs into
    us: it cannot tell "the machine is bad" from "we are slow", and the floor
    used to sit at our own ceiling -- the 20 August sag, see `blame_machine`.

    Zero means "could not measure"; the floor then stays as it was.
    """
    import urllib.request
    try:
        t0 = time.time()
        # A megabyte is enough and fits a narrow channel: three megabytes at
        # 2.3 Mbit/s did not fit the term and the measurement returned zero --
        # the insurance against a narrow channel broke on one. The header is
        # mandatory too: without it Cloudflare answers 403, the measurement is
        # zero again, and the insurance switches itself off in silence.
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
    """Rent a machine, wait for ssh and measure the channel to it.

    A bad machine is filtered out here in twenty seconds instead of fifteen
    minutes into uploading input files. Each attempt gets its own watchdog: an
    abandoned one left alive reaches its deadline and destroys the next
    machine, which belongs to someone else.
    """
    # Rejected machines are excluded for good, not for one run: without that,
    # preferring warm machines leads back onto the same rake.
    ours = _our_downlink_mbps()
    limit = _min_link_mbps()
    floor = limit
    # WRITTEN DOWN BECAUSE IT DECIDES. `ours` sets the rejection floor and
    # gates the permanent blacklist, and until now it existed only in the log
    # line below -- so the two prose accounts of the 3 September incident could
    # disagree (1.8 against 2.8 Mbit/s) with no record able to settle it.
    rec.our_downlink_mbps = ours or None
    if ours:
        # A machine cannot give us more than we can take. Demanding over half
        # of our own channel from it is the limit of sense.
        floor = min(limit, 0.5 * ours)
        log(f"our downlink ~ {ours:.1f} Mbit/s, "
            f"machine rejection floor {floor:.2f} Mbit/s")
        if ours < 2 * limit:
            log("WARNING: our channel is narrow -- the fetch will be slow")

    # The best anyone has ever given US over ssh. Empty until someone is
    # measured: without this witness `blame_machine` blames nobody.
    best_link = [0.0]

    def _blame(offer: dict, reason: str) -> None:
        blame_machine(offer, reason, ours=ours, link=link,
                      best_link=best_link[0])

    avoid: list[int] = list(ledger.bad_machines())
    undead = undead if undead is not None else []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Do not rent a machine there is no time left for -- the flip side of
        # counting the budget from `t0`: at a short `timeout_minutes` the
        # remainder went negative, `Budget` handed out a deadline IN THE PAST,
        # and the watchdog destroyed a freshly rented machine 15 seconds later
        # (timeout_minutes=30, attempts of 480 s: on the fifth the ceiling is
        # -2 min). Paying for a machine we kill ourselves is worse than saying
        # aloud that there is no time.
        left = spec.timeout_minutes * 60 - (time.time() - t0)
        if left <= ATTEMPT_LIMIT_S:
            raise SystemExit(
                f"no time left for an attempt: {left/60:.1f} min to the "
                f"ceiling, one attempt takes up to "
                f"{ATTEMPT_LIMIT_S/60:.0f} min "
                f"({attempt - 1} made). Raise timeout_minutes, or find "
                f"out why machines are rejected.")
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
        log(f"taking #{offer['id']} at ${dph:.3f}/hour, "
            f"disk {spec.host.disk_gb} GB"
            + (f" (attempt {attempt})" if attempt > 1 else ""))

        guard = threading.Event()
        guards.append(guard)
        budget = Budget(spec, dph, t0)
        # A cell of its own per attempt, not the shared `state`. The watchdog
        # of an abandoned attempt outlives it on purpose -- when `destroy`
        # failed, the branch below leaves it to finish the machine off. But
        # `state["iid"]` by then pointed at the NEXT machine, and the old
        # watchdog destroyed that one mid-work, exactly what this function's
        # docstring forbids.
        #
        # `m=mine` is not decoration: a closure in a loop holds the VARIABLE,
        # not the value; without it every watchdog would look into the last
        # attempt's cell -- the same trouble, quieter.
        mine: dict = {"iid": None, "t_create": None}
        threading.Thread(target=_watchdog,
                         args=(vast, lambda m=mine: m["iid"], budget, guard),
                         daemon=True).start()

        def _remember(new_id: int, m=mine):
            state["iid"] = m["iid"] = new_id
            # The moment the successful machine was CREATED: `setup_s` counts
            # from here, and a copy per attempt tells what the REJECTED machine
            # cost.
            state["t_create"] = m["t_create"] = time.time()
            rec.instance_id = new_id

        def _charge(m=mine, price=dph):
            """Write down the money this attempt ate.

            A rejected machine bills from the second it was created, and until
            this fix its rental never entered `cost_usd` AT ALL: `rec.dph` is
            assigned only after a successful rental, so a run that fell through
            reached the ledger with `dph` = 0. The ledger holds 13 such
            records: 9268 seconds of runs for $0.102 -- traffic alone, and not
            one second of rental for five machines taken.
            """
            t = m.get("t_create")
            if t is None:
                return 0.0                 # no instance was created -- nothing to pay for
            spent = price * (time.time() - t) / 3600
            rec.reject_usd += spent
            rec.reject_n += 1
            m["t_create"] = None           # the same second is not counted twice
            log(f"  the rejected machine cost ${spent:.4f} "
                f"({(time.time() - t)/60:.1f} min at ${price:.3f}/hour); "
                f"rejections total ${rec.reject_usd:.4f} "
                f"over {rec.reject_n} machines")
            return spent

        # THE OFFER MAY HAVE DIED between the search and the creation: the
        # market is taken apart in seconds and vast answers 400 on someone
        # else's ask. This used to kill the WHOLE run with four attempts left
        # and a full market next door, and a repeat of the same command took
        # the same dead offer. One failed attempt, not a refusal.
        try:
            vast.create(int(offer["id"]), spec, on_created=_remember)
        except Exception as e:
            log(f"offer #{offer['id']} not taken ({type(e).__name__}: "
                f"{str(e)[:90]}) -- taking the next")
            _charge()          # usually zero: no instance was created
            # `or 0` here meant "avoid a machine without a machine_id as
            # machine number zero" -- avoid nobody, while filtering out a
            # foreign offer whose machine_id really is 0. An empty field is
            # named aloud, not turned into a number.
            mid = offer.get("machine_id")
            if mid is None:
                log(f"  offer #{offer['id']} has no machine_id -- "
                    f"this machine can come again")
            else:
                avoid.append(int(mid))
            guard.set()
            continue
        if ssh_key:
            vast.attach_key(state["iid"], ssh_key)

        log(budget.describe())
        log("waiting for the image download and the container start...")
        try:
            box = connect(vast, state["iid"], spec, ssh_key,
                          attempt_limit=ATTEMPT_LIMIT_S)
            # The probe measures BY TIME and returns an honest speed -- no
            # false zeros (see its docstring). It used to ask for exactly 4 MB
            # within 25 s and return 0.0 on a shortfall: "we failed to receive"
            # written down as "the machine is broken".
            link = box.probe()
            # The floor here is the EFFECTIVE one (`floor`), not the registry
            # `limit`. With the registry one, a machine that passed a floor
            # loosened by our narrow channel went into the ledger with
            # `download_mbps` = 0.0 -- indistinguishable from "the probe did
            # not work". Now everything we ACCEPT is measured, and `None` means
            # "not measured".
            down = box.probe_download() if link >= floor else None
            connect_failed = False
        except (RuntimeError, OSError) as e:
            connect_failed = True
            log(f"machine did not reach ssh in "
                f"{ATTEMPT_LIMIT_S/60:.0f} min ({e}) -- taking another")
            link, down = 0.0, None
        best_link[0] = max(best_link[0], link)
        rec.link_mbps = link
        rec.download_mbps = down          # None = NOT MEASURED, not "zero"
        if link >= floor and (down is None or down >= MIN_DOWNLOAD_MBPS):
            # TWO DECIMALS, NOT A ZERO. The rejection line next door prints
            # `.2f`, this one printed `.0f` -- anything below one showed as
            # zero. Measured 3 September 2026: an accepted machine reported "to
            # us 0 Mbit/s" against a floor of 0.15, i.e. the acceptance line
            # claimed exactly what its neighbour rejects for. A quantity
            # destroyed at the printout is "done" instead of a number, from the
            # other end.
            log(f"channel: to us {link:.2f} Mbit/s, from the world "
                + (f"{down:.0f} Mbit/s" if down is not None
                   else "not measured"))
            return box, dph, budget

        if not link and connect_failed:
            pass          # the reason is already named above
        elif not link:
            # A zero is the probe timing out, not "unknown". Both branches
            # below used to be false at zero and the machine died silently: ssh
            # ready in 5 s in the log, then nothing, then "DESTROYED" half a
            # minute later. Five in a row looked like "the market is bad".
            log(f"ZERO bytes to us in the time allowed -- taking another. "
                f"This is the machine: the probe measures by time, so a "
                f"live channel would give some number, however small")
            # And onto the permanent list -- the case the list was made for. A
            # 62 kbit/s machine does not give 4 MB in 25 seconds, so `probe`
            # returns 0.0 and lands HERE, not in the `link < floor` branch
            # below where the only `mark_bad` used to stand. Until this line no
            # machine with a dead channel ever reached the list -- and such a
            # machine counts as warm alongside the rest.
            _blame(offer, f"zero bytes to us in the time allowed "
                          f"(floor {floor:.2f} Mbit/s)")
        elif link < floor:
            log(f"channel to us only {link:.2f} Mbit/s "
                f"(need {floor:.2f} or more) -- taking another")
            _blame(offer, f"channel to us {link:.2f} Mbit/s")
        elif down is not None and down < MIN_DOWNLOAD_MBPS:
            log(f"machine pulls only {down:.0f} Mbit/s from the world "
                f"(need {MIN_DOWNLOAD_MBPS:.0f} or more) -- taking another")
        else:
            # A REJECTION WITH NO REASON NAMED. The branch above used to be a
            # bare `elif link:`, i.e. a catch-all wearing the downlink
            # rejection's words -- and since `MIN_DOWNLOAD_MBPS` is 0.0 the
            # real downlink test can never fail, so anything landing here got
            # "pulls only N (need 0 or more)" printed over it. Now the four
            # branches say what they mean and this one says that they did not
            # cover the case, which is the difference between a zero from a
            # check and a zero from not understanding.
            log(f"machine rejected and THE REASON WAS NOT NAMED: to us "
                f"{link:.2f} Mbit/s against a floor of {floor:.2f}, from the "
                f"world {down if down is not None else 'not measured'} "
                f"against {MIN_DOWNLOAD_MBPS}. This is a hole in the branches "
                f"above, not a property of the machine")
        # The pulse must stop BEFORE the machine is abandoned: otherwise our
        # own thread keeps reviving it and the dead-man's watch never fires.
        #
        # A SILENT `except Exception: pass` STOOD HERE AND HID EXACTLY THAT --
        # the story is in `connect`: unbound `box`, `UnboundLocalError`
        # swallowed, machine off to `undead` with a live pulse and not a line
        # in the log. `connect` now stops what it started; this is a backstop,
        # and it SPEAKS.
        try:
            box.stop_heartbeat()
        except Exception as e:                                  # noqa: BLE001
            log(f"WARNING: the abandoned machine's pulse still runs "
                f"({e}) -- our own thread may be holding its dead-man's "
                f"watch off; check `books ls`")
        # The destruction result is not thrown away: on failure the machine is
        # alive and its id must not be cleared -- `finally` would not touch it
        # and its watchdog would be silenced, leaving nobody watching at all.
        if vast.destroy(int(state["iid"])):
            _charge()                      # this machine's money into the ledger
            state["iid"] = mine["iid"] = None
            guard.set()
        else:
            log(f"instance {state['iid']} could not be destroyed -- "
                f"leaving its watchdog and finishing it off at the end")
            # Money counted up TO this second and the price passed on: the
            # machine bills after our failed attempt too and is finished off in
            # `finally`, where the remainder is added -- otherwise an abandoned
            # machine would cost the same zero as one never created.
            _charge()
            undead.append({"iid": int(state["iid"]), "dph": dph,
                           "since": time.time()})
        mid = offer.get("machine_id")
        if mid is not None:
            avoid.append(mid)

    raise RuntimeError(
        f"in {MAX_ATTEMPTS} attempts no machine was found with a channel "
        f"from {floor:.2f} Mbit/s"
        + (f"; our own channel was {ours:.1f} Mbit/s at the time -- it "
           f"may be the cause" if ours else ""))


def run_job(spec: JobSpec, outdir: str, ssh_key: str | None = None,
            keep: bool = False, reuse: int | None = None,
            dry_run: bool = False, report: dict | None = None,
            keep_until: float | None = None,
            keep_usd: float | None = None) -> int:
    """A full run. Returns the job's return code.

    `report` is an optional dict taking the `instance_id` of the LIVE machine
    (i.e. only under `keep`, else `None`), its hourly price and the spend. The
    id puts the second and third passes on the same machine; price and spend
    let a chain of passes know how much budget is left instead of starting a
    new one each pass. The spend counts rejected machines TOO, or the chain
    would think a failed rental cost it nothing.

    `keep_until` is the ABSOLUTE moment up to which holding the machine under
    `--keep` makes sense, `keep_usd` the money the chain has left. The default
    four-hour watch is far too much between passes of one command: if our
    process dies in between, the card bills until morning.

    Absolute, not a duration: the first revision counted the remainder at the
    start of a pass and set the watch at the end, so a machine that began the
    last pass with a minute left got a hundred-minute watch AFTER it finished.
    And with money in it: computed from minutes alone, the watch turned a $1.00
    ceiling into an actual nine on a $2/hour card.
    """
    vast = Vast()
    outdir = os.path.abspath(outdir)

    rec = ledger.Run(job=spec.name, image=spec.image, gpu=spec.host.gpu,
                     image_gb=spec.image_gb)
    old_signals = _install_signals()
    t0 = time.time()
    # The id lives in a mutable cell: the watchdog and the cleanup must see it
    # right after the instance is created, not after create() returns.
    state = {"iid": reuse}
    offer, done = None, threading.Event()

    if dry_run:
        if reuse:
            log(f"dry run: would compute on instance {reuse}")
        else:
            warm = _warm(spec)
            offer = vast.pick(spec.host, spec.image_gb, spec.minutes, warm,
                              payload_gb=spec.payload_gb,
                              warmup_s=spec.warmup_s)
            log(f"dry run -- would take #{offer['id']} "
                f"at ${float(offer['dph_total']):.3f}/hour")
        _restore_signals(old_signals)
        return 0

    # The local directory needs cleaning too: rsync runs without --delete, so
    # the last run's pages stayed among the new ones -- and _run_facts picked
    # up the old run.json and progress.json and wrote them into the ledger as
    # this run's data, forging the very numbers a machine is chosen by.
    if not spec.resume and os.path.isdir(outdir) and os.listdir(outdir):
        import shutil
        shutil.rmtree(outdir)
        log(f"local directory {outdir} cleared of the previous run")
    os.makedirs(outdir, exist_ok=True)
    guards: list[threading.Event] = []
    # Machines that had to be abandoned but could not be destroyed: finished
    # off at the end, or they bill until their own dead-man's watch.
    undead: list[int] = []
    # `box` is declared BEFORE the try: the cleanup stops the pulse through it,
    # and a machine may not be rented at all (five attempts finding no
    # acceptable channel). Then `box` did not exist and the cleanup raised
    # "cannot access local variable 'box'" over the real reason for refusing.
    box = None
    try:
        # A machine left behind does not live forever: the watch kills it after
        # KEEP_GRACE_S. Without this check `--reuse` on a dead instance waited
        # for it up to boot_limit -- thirty-five minutes of "status=None".
        if reuse:
            try:
                gone = vast.instance(reuse) is None
            except Exception as exc:
                # Could not ask -- take the machine to be alive. Otherwise we
                # rent a second card while the first keeps billing.
                log(f"could not check instance {reuse} ({exc}) -- "
                    f"taking it to be alive")
                gone = False
            if gone:
                log(f"instance {reuse} no longer exists -- taking a new one")
                reuse = None
                state["iid"] = None

        if reuse:
            log(f"reusing instance {reuse} -- no cold start")
            inst = vast.instance(reuse) or {}
            # The price is not invented. `or 0.5` used to stand here and a
            # CEILING was built out of the invented number: at the JobSpec
            # defaults (budget_usd=1.00, timeout_minutes=90) a $2.00/hour card
            # got 90 minutes instead of 30 -- three times the declared, and
            # only because the term hit the timeout; without it, four. And `or`
            # swallowed a legal 0.0 on top: a zero from not knowing must not
            # become a measurement.
            raw_dph = inst.get("dph_total")
            if raw_dph is None:
                raise SystemExit(
                    f"instance {reuse} reports no price (dph_total) -- "
                    f"nothing to count a budget from. Look: books ls")
            dph = float(raw_dph)
            # The price into the record AT ONCE, not after a successful
            # connect: the machine already bills, and a run that fell through
            # on ssh would otherwise reach the ledger free -- the rejected-
            # machine trouble again, on the `--reuse` branch.
            rec.dph = dph
            rec.instance_id, rec.machine_id = reuse, inst.get("machine_id")
            budget = Budget(spec, dph, t0)
            guards.append(done)
            threading.Thread(target=_watchdog,
                             args=(vast, lambda: state["iid"], budget, done),
                             daemon=True).start()
            log(budget.describe())
            log("waiting for the image download and the container start...")
            # The same attempt ceiling as on the rental branch. Without it
            # `boot_limit` = 2100 s went here: thirty-five minutes of waiting
            # on a machine that already bills.
            box = connect(vast, reuse, spec, ssh_key,
                          attempt_limit=ATTEMPT_LIMIT_S)
        else:
            box, dph, budget = _rent(vast, spec, ssh_key, state, rec,
                                     guards, t0, undead)

        rec.dph = dph
        # Whether the last line of defence is armed -- INTO THE LEDGER, not
        # only into that evening's log: a run on a machine without the watch
        # differs from one with it in that a forgotten machine bills until
        # someone kills it by hand, and that must be provable afterwards.
        rec.extra["deadman"] = box.deadman
        # setup_s runs from the CREATION of the successful machine to a ready
        # ssh, as the ledger field declares. The previous revision measured the
        # whole run-up -- our channel probe, every rejected attempt, every
        # offer search, both probes -- and `fit()` divided a constant 0.06 GB
        # of image by that, printing "channel efficiency 0.0052" against a
        # constant of 0.05: a tenfold discrepancy, purely arithmetic.
        t_create = state.get("t_create") or t0
        rec.setup_s = time.time() - t_create
        rec.reject_s = t_create - t0
        log(f"ready in {rec.setup_s/60:.1f} min "
            f"({rec.reject_s/60:.1f} min went on rejections)")

        t1 = time.time()
        rc = execute(box, spec, outdir, deadline=budget.deadline)
        if rc != 0:
            # Look into the vLLM log: "CUDA unknown error" is a broken card on
            # the host, not our trouble, and such a machine will come back. Its
            # channel is fine, so the probe lets it through.
            try:
                vl = os.path.join(outdir, "vllm.log")
                if os.path.exists(vl):
                    tail = open(vl, encoding="utf-8", errors="replace").read()
                    if "CUDA unknown error" in tail or "no CUDA-capable device" in tail:
                        ledger.mark_bad(rec.machine_id,
                                        "the card does not initialise (CUDA)")
                        log(f"machine {rec.machine_id} blacklisted: the "
                            f"card does not initialise")
            except Exception:
                pass
        rec.run_s = time.time() - t1
        rec.extra.update(_run_facts(outdir))
        rec.ok = rc == 0
        if rc != 0:
            rec.note = f"the job returned {rc}"
            log(f"the job ended with code {rc} -- result fetched in part")
        return rc

    except _Interrupted as e:
        rec.note = f"interrupted: {e}"
        log(f"interrupted ({e}) -- cleaning up after myself")
        return 130
    except (Exception, SystemExit) as e:
        # SystemExit is caught ON PURPOSE: a BaseException, it passed straight
        # through `except Exception`, and a failure -- "no offers", "no price",
        # "no time left" -- reached the ledger with an empty note and a zero
        # price, looking like a free success. A zero from not knowing.
        rec.note = f"{type(e).__name__}: {e}"
        raise
    finally:
        _ignore_signals()          # first of all: the cleanup must not be interrupted
        done.set()
        for g in guards:           # watchdogs of every attempt, abandoned ones too
            g.set()
        for dead in undead:
            # The rest of an abandoned machine's rental: from the second
            # already counted in `_rent` to this one, or the minutes between
            # "could not destroy" and the finishing off cost nothing.
            rec.reject_usd += dead["dph"] * (time.time() - dead["since"]) / 3600
            if vast.destroy(int(dead["iid"])):
                log(f"abandoned instance {dead['iid']} finished off")
            else:
                log(f"WARNING: instance {dead['iid']} not destroyed and "
                    f"still billing -- kill it by hand: "
                    f"books down {dead['iid']}")
        iid = state["iid"]
        elapsed = time.time() - t0
        rec.total_s = elapsed
        # Rental counts from the CREATION of the successful machine, not from
        # the start of the run: before that it did not exist. Rejected machines
        # are a separate term, their own time at their own price. `rec.dph *
        # elapsed` was wrong twice: it charged the successful machine minutes
        # when it did not yet exist (a run in the ledger carries 211 s of
        # rejection), and a run that fell through on renting went free at
        # `rec.dph` = 0 and five machines taken cost $0.000 -- 13 records
        # out of 111, see `_charge`.
        alive_s = time.time() - (state.get("t_create") or t0)
        # Traffic counts the payload, not the image alone: wheels and weights
        # are 7.2 GB against 0.06, and without them the ledger figure was some
        # hundredfold low. The estimator in pricing.py counts the same way.
        rec.cost_usd = (rec.dph * alive_s / 3600 + rec.reject_usd
                        + rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024)
        # The pulse stops BEFORE the successful machine is destroyed -- last of
        # the local ways, not first thing in the cleanup. The dead-man's watch
        # on the card is the one of the four that needs neither our key nor our
        # process, and our thread's `touch /root/.alive` every 30 seconds keeps
        # it off.
        #
        # DO NOT MOVE IT EARLIER. The argument is computed, not eyeballed:
        #
        #   * `stop_heartbeat` does `join(timeout=2)` (`box.py`), i.e. it
        #     BLOCKS; before `_ignore_signals()` it hands those two seconds to
        #     Ctrl-C, and "the cleanup must not be interrupted" stands there
        #     for a reason;
        #   * the `undead` loop above finishes off up to MAX_ATTEMPTS = 5
        #     machines at `Vast.RETRY_S` = (4, 8, 16, 32, 60) -- up to 120 s of
        #     pauses each, 600 s per loop, against DEADMAN_GRACE_S = 900 that
        #     `tests/test_rent_deadlines.py` guards for ONE destroy, not five.
        #     An earlier stop starts the watch's clock before those minutes;
        #   * `box.py`, next to `SHORT_CMD_S`, tells how going to the network
        #     from a `finally` on a silent machine used to end.
        #
        # Abandoned machines stay watched only since the fix in `connect`:
        # before it both left for `undead` with a live pulse. Three
        # `stop_heartbeat` calls exist -- `connect` on failure, `_rent` before
        # abandoning, this one -- and
        # `test_a_failed_connect_leaves_no_machine_with_a_live_pulse` guards
        # that.
        try:
            if box is not None:
                box.stop_heartbeat()
        except Exception as e:
            log(f"pulse not stopped: {e}")
        if iid and not keep:
            # The result is inspected, as everywhere else: this was the one
            # `destroy` in the file without a check, and five failed tries
            # printed "COULD NOT DESTROY" while the next line reported
            # "total N min" and returned 0 -- with a live billing machine.
            if not vast.destroy(int(iid)):
                log(f"WARNING: instance {iid} NOT DESTROYED and still "
                    f"billing -- kill it by hand: books down {iid}")
                rec.note = ((rec.note + "; ") if rec.note else "") + \
                    f"instance {iid} not destroyed, ${rec.dph:.3f}/hour"
        elif iid:
            # The operator leaves on purpose; the watch on the machine does not
            # know it and would destroy the instance in its 15 minutes. A
            # longer term: --keep is for the next run, not for days of paying.
            if keep_until is None:
                grace = KEEP_GRACE_S
            else:
                left_s = keep_until - time.time()
                if keep_usd is not None:
                    left_usd = keep_usd - rec.cost_usd
                    left_s = min(left_s,
                                 left_usd / max(rec.dph, 1e-6) * 3600)
                # Ten minutes for the changeover -- enough for the next pass to
                # connect, not enough to cost anything noticeable.
                grace = max(300.0, left_s + 600)
            try:
                box.set_deadman(grace)
                log(f"the machine's dead-man's watch reset to "
                    f"{grace/60:.0f} min without a run")
            except Exception as e:
                log(f"could not reset the dead-man's watch ({e}) -- the "
                    f"instance will destroy itself in 15 minutes")
            log(f"--keep: instance {iid} LEFT ALIVE AND BILLING. "
                f"Next run: --reuse {iid}; kill it: books down {iid}")
        if report is not None:
            # The LIVE machine, not the last one seen. `state["iid"]` is not
            # cleared after a destruction, and the report called a destroyed
            # machine live: the next pass took it as `--reuse` and stood
            # waiting for it until the attempt ceiling, over nothing. A live
            # instance remains exactly under `--keep`; a machine that FAILED to
            # be destroyed is alive too but must not be reused -- the operator
            # has been told to kill it by hand and `note` records it.
            report["instance_id"] = iid if (keep and iid) else None
            report["dph"] = rec.dph
            report["cost_usd"] = rec.cost_usd
        ledger.append(rec)
        # A quantity, not "done", and by its terms: one sum hides that half the
        # money went on machines we never even accepted.
        log(f"total {elapsed/60:.1f} min ~ ${rec.cost_usd:.3f} "
            f"(rent {alive_s/60:.1f} min at ${rec.dph:.3f}/hour = "
            f"${rec.dph * alive_s / 3600:.3f}"
            + (f"; {rec.reject_n} machines rejected for ${rec.reject_usd:.3f}"
               if rec.reject_n else "")
            + (f"; traffic $"
               f"{rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024:.3f})")
            + f"; ledger: {ledger.LEDGER}")
        _restore_signals(old_signals)
