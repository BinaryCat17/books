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
from booksmith.core import knobs
from .spec import JobSpec
from .vast import Vast
from booksmith.core.log import log
from booksmith.core.errors import Refusal


class Budget:
    """A hard ceiling, on money and on time both.

    The deadline follows the price of this offer, not abstract minutes: $1.00
    on a $0.34/hour card is 2.9 hours, on a $2 card 30 minutes.
    """

    def __init__(self, spec: JobSpec, dph: float, t0: float | None = None):
        self.started = time.time()
        # Time runs from the start of the run (`t0`), not of the attempt: a
        # term per attempt hands every rejected machine another full one. Money
        # counts this machine alone -- a destroyed one bills no more.
        self.t0 = self.started if t0 is None else t0
        self.eaten = self.started - self.t0
        by_money = spec.budget_usd / max(dph, 1e-6) * 3600
        by_time = spec.timeout_minutes * 60 - self.eaten
        # A negative remainder is trouble upstream, not "zero budget": the
        # machine is already rented, and silence lets the watchdog kill it.
        if by_time <= 0:
            raise Refusal(
                f"the time budget is spent BEFORE the count begins: "
                f"attempts ate {self.eaten/60:.1f} min of a "
                f"{spec.timeout_minutes:.0f} min ceiling")
        self.seconds = min(by_money, by_time)
        self.dph = dph
        self.limited_by = "money" if by_money < by_time else "time"
        # A knob that limits nothing is worse than a missing one: a run cannot
        # cost more than `max_dph * timeout_minutes` by construction, so at the
        # defaults $0.60/hour x 1.5 h = $0.90 against $1.00 and `budget_usd`
        # never fires. The price cap and the term are the real defence, and
        # rejected machines cost money outside this count altogether.
        self.ceiling_usd = spec.host.max_dph * spec.timeout_minutes / 60
        self.money_unreachable = self.ceiling_usd <= spec.budget_usd

    @property
    def deadline(self) -> float:
        return self.started + self.seconds

    @property
    def spent(self) -> float:
        return self.dph * (time.time() - self.started) / 3600

    def describe(self) -> str:
        # A number, not "done": what the attempts ate explains a ceiling
        # shorter than the declared one.
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
    silence, and this is the last line of defence, the main thread possibly
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
            if vast.destroy(iid):
                return
        except Exception as e:
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

    A second Ctrl-C is a reflex once the first looks hung, and landing in
    `destroy` it would carry the process past the destruction, leaving the
    instance alive and billing.
    """
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, signal.SIG_IGN)
        except ValueError:
            pass


def _run_facts(outdir: str) -> dict:
    """What the job itself reported about the run, for the ledger.

    The runner knows nothing about OCR and must not: it picks up the small json
    files the job left in the result directory.
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

    The value is not the image cache -- 54 MB, seconds -- but vast's own ssh
    layer, built on a fresh machine out of a Debian index and near a hundred
    packages: six minutes, against thirty-four seconds where it is already done.
    """
    bad = set(ledger.bad_machines())
    # Order matters: the fast first by ascending compute time, then the rest of
    # the warm ones, freshest first. An advertised speed is advertising.
    fast = [m for m in ledger.fast_machines(spec.image, job=spec.name)
            if m not in bad]
    slow = set(ledger.slow_machines(spec.image, job=spec.name))
    warm = [m for m in ledger.warm_machines(spec.image)
            if m not in bad and m not in fast and m not in slow]
    # A number, not silence: rejection by time works only within one job, so a
    # new book's first run has no history and `slow` is empty for a reason other
    # than every machine being good.
    log(f"machine preference: {len(fast)} fast, {len(warm)} warm, "
        f"{len(slow)} slow ones rejected"
        + ("" if slow else f" (no history for job '{spec.name}' -- "
                           f"nothing rejected by time)"))
    return fast + warm


def connect(vast: Vast, iid: int, spec: JobSpec, ssh_key: str | None,
            attempt_limit: float = 480.0) -> Box:
    """Wait for the machine and for ssh. One term for the whole attempt.

    One term, and no second ceiling inside it: an inner one cuts off a machine
    that is pulling the image fine, while `t_end` bounds the attempt anyway.
    """
    t_end = time.time() + attempt_limit
    # The boot wait is inside the common term and has no ceiling of its own.
    # The thirty-second floor is needed: an attempt begun at the end of the
    # term could not otherwise even ask for status.
    vast.wait_running(iid, timeout=max(30.0, t_end - time.time()))
    # Attaching the key straight after creating the instance is a race: a key
    # attached before the container exists sometimes never reaches
    # authorized_keys. Repeat once it does; attaching is idempotent.
    if ssh_key:
        vast.attach_key(iid, ssh_key)
    user, host, port = vast.ssh_target(iid)
    log(f"ssh {user}@{host}:{port}")
    box = Box(user, host, port, ssh_key, spec.workdir)
    box.wait_ready(timeout=max(60.0, t_end - time.time()))
    # The pulse right after ssh: from now on the machine destroys itself if the
    # operator falls silent (ONSTART in vast.py).
    box.start_heartbeat()
    # Whoever started the pulse stops it if things go wrong: everything below
    # goes to the network, and `box` reaches the caller only at `return`, whose
    # variable is until then unbound or holds the previous attempt's machine. A
    # machine abandoned with a live pulse has our own thread holding its
    # dead-man's watch off -- the one kill path of four that needs neither our
    # key nor our process.
    try:
        # And at once: is the one this pulse is addressed to armed? One short
        # command over the multiplexed connection, before anything is uploaded
        # -- a missing last line of defence is learnt in the first minute.
        box.check_deadman()
    except BaseException:
        # `BaseException`, not `Exception`: on Ctrl-C the pulse must fall
        # silent too, or an interrupted run leaves the machine immortal.
        try:
            box.stop_heartbeat()
        except Exception as e:
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
            raise Refusal(f"no such file: {local}")
        box.push(local, remote_rel)
        log(f"  {os.path.basename(local)} -> {remote_rel}")

    # A warm machine still holds the last run's result directory and the job
    # counts the work done, so an unwanted resume computes one page of twenty
    # and the run looks successful and costs money.
    if not spec.resume:
        # With a term and with a check: an unnoticed failure leaves the last
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
        # Knob values are shell-quoted: the string is built for a foreign shell
        # out of the operator's environment, where a value with a space tears
        # the command in two and one with `;` or `$(...)` runs as code. The name
        # is checked instead of quoted -- it must be a legal shell variable name
        # -- and refusing here beats a syntax error after vLLM is up.
        bad = [k for k in spec.env if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)]
        if bad:
            raise Refusal(f"knob names unfit for a shell: {bad}")
        env = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in spec.env.items())
        cmd = f"cd {shlex.quote(spec.workdir)} && {env} {spec.command}".strip()
        rc, _ = box.run(cmd, deadline=deadline)
    finally:
        box.stop_sync()
        # What each exclusion costs, before it fires and as a number, measured
        # dry and so for zero bytes transferred.
        if spec.pull_exclude:
            try:
                box.weigh_exclude(spec.outputs, spec.pull_exclude, outdir)
            except Exception as e:
                log(f"  exclusions not weighed ({e}) -- fetching as is")
        log("fetching the whole result...")
        if box.pull(spec.outputs, outdir,
                    exclude=spec.pull_exclude) != 0 and rc == 0:
            # The job finished and the result did not arrive -- no success: an
            # incomplete parse must not be handed over as a finished one.
            log("WARNING: the result did not arrive in full")
            rc = 75
    return rc


# What a witness must itself reach before it may condemn another machine: not
# "a good speed" but "a stream at all" -- 0.5 Mbit/s is some 750 KB over a
# twelve-second probe, above every reading of our own sick path (0.25, 0.34) and
# of a broken machine (0.06). It must stay well under any sane `MIN_LINK_MBPS`,
# or the blacklist can never fire: a machine is judged only after rejection, so
# every reading in `best_link` is below the rejection floor.
WITNESS_MBPS = 0.5


def _min_link_mbps() -> float:
    """The rejection floor from the registry, refused if it is not a number.

    `float()` accepts `nan` and `inf`, and `nan` compares False with everything:
    at `MIN_LINK_MBPS=nan` every machine falls through the branches with no
    reason named. A typo that costs money is a refusal before the first rental.
    """
    # One reader for all of them: the validation lives in `knobs.number`.
    return knobs.number("MIN_LINK_MBPS")



# Speed "from the world" does not reject yet, it only goes to the ledger: a
# threshold set off two points is the mistake already made. At 0.0 nothing is
# refused, which is why the branch below is the negation of the acceptance test
# rather than a catch-all -- raise this and that branch starts firing.
MIN_DOWNLOAD_MBPS = 0.0
# Five attempts: a rejection costs about two minutes, and three unusable
# machines in a row happen, all three out of one cluster.
MAX_ATTEMPTS = 5

# The ceiling of one attempt: container start plus ssh. Two minutes is
# impossible -- vast builds its ssh layer for some three minutes -- and five
# proved too harsh as well, vast counting the container started before sshd
# listens, so "Connection refused" drags on for four and a half. A machine
# abandoned on this ceiling is not bad forever; only a broken channel earns
# the permanent list.
ATTEMPT_LIMIT_S = 480.0

# The dead-man's term under --keep: the machine is left on purpose, but not
# forever. Four hours -- a warm machine the same evening, and not a forgotten
# instance eating the budget overnight.
KEEP_GRACE_S = 4 * 3600


def blame_machine(offer: dict, reason: str, *, ours: float, link: float,
                  best_link: float, mark=None, say=None,
                  ours_now: float | None = None) -> bool:
    """Onto the permanent blacklist -- but only when the machine is at fault.

    At module level, not a closure, so a check can call it and a mutation can
    spoil it. The probe measures the path from the machine to us and runs into
    us, so a machine is condemned only on a witness: another that gave us three
    times more over the same ssh and cleared `WITNESS_MBPS` itself. `limit` is
    absent from the signature -- loosening the rejection floor may not make a
    permanent ban easier -- and the two silences are named apart, since "nobody
    has given us anything usable" is not "no witness against this one".
    """
    mark = mark or ledger.mark_bad
    say = say or log
    if not ours:
        say("  our channel is not measured -- NOT blacklisting: the "
            "probe's zero may have been ours")
        return False
    # A path that sagged mid-loop is not a run of bad machines: `best_link` is a
    # maximum and never decays, so a witness recorded while we were fast goes on
    # condemning after we have slowed. Our own path is re-measured here, and a
    # halving since the loop began makes the contrast ours and not theirs.
    if ours_now is not None and ours_now < 0.5 * ours:
        say(f"  NOT blacklisting: our own downlink has fallen from "
            f"{ours:.1f} to {ours_now:.1f} Mbit/s since this rental began, so "
            f"the machine that gave us {best_link:.2f} was measured on a "
            f"different path than this one. The contrast is OURS")
        return False
    if best_link < WITNESS_MBPS:
        say(f"  NOT blacklisting: the best any machine has given us over ssh "
            f"is {best_link:.2f} Mbit/s, under the {WITNESS_MBPS:.1f} a "
            f"witness must clear -- so nobody has shown this path works, and "
            f"this one's {link:.2f} is as likely ours as its own. The list "
            f"is forever and has no undo")
        return False
    if best_link < 3 * link:
        say(f"  NOT blacklisting: the best ever given us over ssh is "
            f"{best_link:.2f} Mbit/s against {link:.2f} here -- no "
            f"witness against the machine, our own path looks narrow, "
            f"and the list is forever")
        return False
    # The record may not kill the run: `mark_bad` writes a file, and a raise out
    # of the middle of `_rent` abandons a machine that is taken and billing.
    # Failing to write a blacklisting is bad, and doing it in silence is worse.
    try:
        mark(offer.get("machine_id"), reason)
    except Exception as e:
        say(f"  WARNING: machine {offer.get('machine_id')} could NOT be "
            f"written to the blacklist ({e}) -- it will be offered again. "
            f"The run goes on; the list is what failed, not the rental")
        return False
    return True


def _our_downlink_mbps(timeout: float = 20.0, mb: int = 1) -> float:
    """The speed of our own downlink, so machines are not blamed for it.

    The channel probe measures the path from the machine to us and runs into us:
    it cannot tell "the machine is bad" from "we are slow" (see `blame_machine`).
    Zero means "could not measure"; the floor then stays as it was.
    """
    import urllib.request
    try:
        t0 = time.time()
        # A megabyte is enough and fits a narrow channel: three at 2.3 Mbit/s
        # do not fit the term, and the measurement then returns zero, which is
        # the insurance against a narrow channel breaking on one. The header is
        # mandatory too: without it Cloudflare answers 403, zero again.
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
    minutes into uploading input files. Each attempt gets its own watchdog: one
    left alive reaches its deadline and destroys somebody else's next machine.
    """
    # Rejected machines are excluded for good, not for one run: without that,
    # preferring warm machines leads back onto the same rake.
    ours = _our_downlink_mbps()
    limit = _min_link_mbps()
    floor = limit
    # Written down because it decides: `ours` sets the rejection floor and gates
    # the permanent blacklist, and prose is no record of it.
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
        # Our own path is measured again here and not taken from the top of the
        # loop: `ours` is read once, before the first rental, and a path that
        # sags during the loop looks exactly like a run of slow machines. One
        # HTTPS megabyte, spent at most five times per rental.
        blame_machine(offer, reason, ours=ours, link=link,
                      best_link=best_link[0], ours_now=_our_downlink_mbps())

    avoid: list[int] = list(ledger.bad_machines())
    undead = undead if undead is not None else []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Do not rent a machine there is no time left for -- the flip side of
        # counting the budget from `t0`: a negative remainder gives a deadline in
        # the past, and the watchdog destroys the machine seconds after renting.
        left = spec.timeout_minutes * 60 - (time.time() - t0)
        if left <= ATTEMPT_LIMIT_S:
            raise Refusal(
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
        # A cell of its own per attempt, not the shared `state`: the watchdog of
        # an abandoned attempt outlives it on purpose, to finish off a machine
        # `destroy` failed on, and `state["iid"]` by then points at the next
        # machine, which it would destroy mid-work.
        #
        # `m=mine` is not decoration: a closure in a loop holds the variable and
        # not the value, so every watchdog would read the last attempt's cell.
        mine: dict = {"iid": None, "t_create": None}
        threading.Thread(target=_watchdog,
                         args=(vast, lambda m=mine: m["iid"], budget, guard),
                         daemon=True).start()

        def _remember(new_id: int, m=mine):
            state["iid"] = m["iid"] = new_id
            # The moment the successful machine was created: `setup_s` counts
            # from here, and a copy per attempt tells what a rejected one cost.
            state["t_create"] = m["t_create"] = time.time()
            rec.instance_id = new_id

        def _charge(m=mine, price=dph):
            """Write down the money this attempt ate.

            A rejected machine bills from the second it was created, while
            `rec.dph` is assigned only after a successful rental: without this a
            run that fell through would reach the ledger as free.
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

        # The offer may have died between the search and the creation: the
        # market is taken apart in seconds and vast answers 400 on someone
        # else's ask. One failed attempt, then, and not a refusal of the run.
        try:
            vast.create(int(offer["id"]), spec, on_created=_remember)
        except Exception as e:
            log(f"offer #{offer['id']} not taken ({type(e).__name__}: "
                f"{str(e)[:90]}) -- taking the next")
            _charge()          # usually zero: no instance was created
            # An empty `machine_id` is named aloud, not turned into a number:
            # `or 0` would avoid nobody while filtering out a foreign offer
            # whose machine_id really is 0.
            mid = offer.get("machine_id")
            if mid is None:
                log(f"  offer #{offer['id']} has no machine_id -- "
                    f"this machine can come again")
            else:
                # `int(mid)` in both places that write this list: one spelling,
                # and nothing coerced silently.
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
            # The probe measures by time and returns an honest speed, with no
            # false zeros (see its docstring).
            link = box.probe()
            # The floor here is the effective one, not the registry `limit`:
            # everything we accept is measured, and `None` means not measured.
            down = box.probe_download() if link >= floor else None
            connect_failed = False
        except (RuntimeError, OSError) as e:
            connect_failed = True
            log(f"machine did not reach ssh in "
                f"{ATTEMPT_LIMIT_S/60:.0f} min ({e}) -- taking another")
            link, down = 0.0, None
        best_link[0] = max(best_link[0], link)
        rec.link_mbps = link
        rec.download_mbps = down          # None = not measured, not "zero"
        if link >= floor and (down is None or down >= MIN_DOWNLOAD_MBPS):
            # Two decimals, as in the rejection line next door: with `.0f`
            # anything below one shows as zero, and the acceptance line would
            # claim exactly the number its neighbour rejects for.
            log(f"channel: to us {link:.2f} Mbit/s, from the world "
                + (f"{down:.0f} Mbit/s" if down is not None
                   else "not measured"))
            return box, dph, budget

        if not link and connect_failed:
            pass          # the reason is already named above
        elif not link:
            # A zero is the probe timing out, not "unknown": it measures by
            # time, so a live channel gives some number, however small.
            log("ZERO bytes to us in the time allowed -- taking another. "
                "This is the machine: the probe measures by time, so a "
                "live channel would give some number, however small")
            # And onto the permanent list -- the case the list was made for: a
            # dead channel returns 0.0 and lands here rather than in the
            # `link < floor` branch, and such a machine counts as warm.
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
            # A rejection with no reason named: the four branches above say
            # what they mean, so landing here is a hole in them and not a
            # property of the machine.
            log(f"machine rejected and THE REASON WAS NOT NAMED: to us "
                f"{link:.2f} Mbit/s against a floor of {floor:.2f}, from the "
                f"world {down if down is not None else 'not measured'} "
                f"against {MIN_DOWNLOAD_MBPS}. This is a hole in the branches "
                f"above, not a property of the machine")
        # The pulse must stop before the machine is abandoned: otherwise our own
        # thread keeps reviving it and the dead-man's watch never fires.
        # `connect` stops what it started; this is a backstop, and it speaks.
        try:
            box.stop_heartbeat()
        except Exception as e:
            log(f"WARNING: the abandoned machine's pulse still runs "
                f"({e}) -- our own thread may be holding its dead-man's "
                f"watch off; check `books ls`")
        # The destruction result is not thrown away: on failure the machine is
        # alive and its id must not be cleared -- `finally` would not touch it
        # and its watchdog would be silenced, leaving nobody watching at all.
        if vast.destroy(state["iid"]):
            _charge()                      # this machine's money into the ledger
            state["iid"] = mine["iid"] = None
            guard.set()
        else:
            log(f"instance {state['iid']} could not be destroyed -- "
                f"leaving its watchdog and finishing it off at the end")
            # Money counted up to this second and the price passed on: the
            # machine bills after our failed attempt too and is finished off in
            # `finally`, where the remainder is added.
            _charge()
            undead.append({"iid": int(state["iid"]), "dph": dph,
                           "since": time.time()})
        mid = offer.get("machine_id")
        if mid is not None:
            avoid.append(int(mid))

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

    `report` is an optional dict taking the `instance_id` of the live machine
    (only under `keep`, else `None`), its hourly price and the spend, rejected
    machines included, so a chain of passes runs on one machine and one budget.
    `keep_until` is the absolute moment up to which holding the machine makes
    sense and `keep_usd` the money left: absolute, or a pass that began with a
    minute to spare would set a long watch after it finished.
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
    # the last run's pages would stay among the new ones and `_run_facts` would
    # write the old run.json into the ledger as this run's data.
    if not spec.resume and os.path.isdir(outdir) and os.listdir(outdir):
        import shutil
        shutil.rmtree(outdir)
        log(f"local directory {outdir} cleared of the previous run")
    os.makedirs(outdir, exist_ok=True)
    guards: list[threading.Event] = []
    # Machines that had to be abandoned but could not be destroyed: finished
    # off at the end, or they bill until their own dead-man's watch.
    undead: list[int] = []
    # `box` is declared before the try: the cleanup stops the pulse through it,
    # and a machine may not be rented at all, in which case an unbound name
    # would raise over the real reason for refusing.
    box = None
    try:
        # A machine left behind does not live forever: the watch kills it after
        # KEEP_GRACE_S, and `--reuse` on a dead instance would wait out the
        # whole attempt ceiling on "status=None".
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
            # The price is neither invented nor defaulted: a ceiling built from
            # a guessed price is no ceiling, and `or` would swallow a legal 0.0
            # -- a zero from not knowing must not become a measurement.
            raw_dph = inst.get("dph_total")
            if raw_dph is None:
                raise Refusal(
                    f"instance {reuse} reports no price (dph_total) -- "
                    f"nothing to count a budget from. Look: books ls")
            dph = float(raw_dph)
            # The price into the record at once, not after a successful
            # connect: the machine already bills, and a run that fell through on
            # ssh would otherwise reach the ledger free.
            rec.dph = dph
            rec.instance_id, rec.machine_id = reuse, inst.get("machine_id")
            budget = Budget(spec, dph, t0)
            guards.append(done)
            threading.Thread(target=_watchdog,
                             args=(vast, lambda: state["iid"], budget, done),
                             daemon=True).start()
            log(budget.describe())
            log("waiting for the image download and the container start...")
            # The same attempt ceiling as on the rental branch: without it the
            # wait runs on for half an hour on a machine that already bills.
            box = connect(vast, reuse, spec, ssh_key,
                          attempt_limit=ATTEMPT_LIMIT_S)
        else:
            box, dph, budget = _rent(vast, spec, ssh_key, state, rec,
                                     guards, t0, undead)

        rec.dph = dph
        # Whether the last line of defence is armed, into the ledger and not
        # only into the log: on an unarmed machine a forgotten instance bills
        # until someone kills it by hand, and that must be provable afterwards.
        rec.extra["deadman"] = box.deadman
        # setup_s runs from the creation of the successful machine to a ready
        # ssh, as the ledger field declares: measure the whole run-up instead
        # and `fit()` divides the image size by rejections and offer searches.
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
            except Exception as e:
                # Said, not swallowed: with no trace here the operator reads a
                # run that finished, on a machine that will be offered again.
                log(f"WARNING: the CUDA check on machine {rec.machine_id} "
                    f"did not finish ({e}) -- if the card was dead, the "
                    f"machine was NOT blacklisted and will be offered again")
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
        # SystemExit is caught on purpose: a BaseException, it passes straight
        # through `except Exception`, and a refusal would reach the ledger with
        # an empty note and a zero price, looking like a free success.
        rec.note = f"{type(e).__name__}: {e}"
        raise
    finally:
        # Wrapped so the restore always runs: anything raising in here would
        # take `_restore_signals` with it, leaving SIGINT and SIGTERM at
        # `SIG_IGN` and Ctrl-C dead for the rest of the process. A `finally` of
        # its own holds for whatever is added here later; a list of the calls
        # that might throw would not.
        try:
            _ignore_signals()          # first of all: the cleanup must not be interrupted
            done.set()
            for g in guards:           # watchdogs of every attempt, abandoned ones too
                g.set()
            for dead in undead:
                # The rest of an abandoned machine's rental: from the second
                # already counted in `_rent` to this one, or the minutes between
                # "could not destroy" and the finishing off cost nothing.
                rec.reject_usd += dead["dph"] * (time.time() - dead["since"]) / 3600
                if vast.destroy(dead["iid"]):
                    log(f"abandoned instance {dead['iid']} finished off")
                else:
                    log(f"WARNING: instance {dead['iid']} not destroyed and "
                        f"still billing -- kill it by hand: "
                        f"books down {dead['iid']}")
            iid = state["iid"]
            elapsed = time.time() - t0
            rec.total_s = elapsed
            # Rental counts from the creation of the successful machine, not from
            # the start of the run: before that it did not exist. Rejected
            # machines are a separate term, their own time at their own price.
            alive_s = time.time() - (state.get("t_create") or t0)
            # Traffic counts the payload, not the image alone: wheels and weights
            # are 7.2 GB against 0.06. The estimator in pricing.py counts the same.
            rec.cost_usd = (rec.dph * alive_s / 3600 + rec.reject_usd
                            + rec.per_tb * (spec.image_gb + spec.payload_gb) / 1024)
            # The pulse stops before the successful machine is destroyed, last of
            # the local ways: the watch on the card is the one of the four that
            # needs neither our key nor our process, and our thread's `touch
            # /root/.alive` every 30 seconds keeps it off. Not earlier --
            # `stop_heartbeat` blocks for two seconds, which before
            # `_ignore_signals()` would be handed to Ctrl-C, and the `undead` loop
            # above may spend minutes, all of them against the watch's own grace.
            try:
                if box is not None:
                    box.stop_heartbeat()
            except Exception as e:
                log(f"pulse not stopped: {e}")
            if iid and not keep:
                # The result is inspected, as everywhere else: five failed tries
                # printing "COULD NOT DESTROY" must not end in a run that returns
                # 0 over a machine that is alive and billing.
                if not vast.destroy(iid):
                    log(f"WARNING: instance {iid} NOT DESTROYED and still "
                        f"billing -- kill it by hand: books down {iid}")
                    rec.note = ((rec.note + "; ") if rec.note else "") + \
                        f"instance {iid} not destroyed, ${rec.dph:.3f}/hour"
            elif iid:
                # The operator leaves on purpose; the watch on the machine does
                # not know it and would destroy the instance in its 15 minutes. A
                # longer term, but --keep is for the next run, not for days.
                if keep_until is None:
                    grace = KEEP_GRACE_S
                else:
                    left_s = keep_until - time.time()
                    if keep_usd is not None:
                        left_usd = keep_usd - rec.cost_usd
                        left_s = min(left_s,
                                     left_usd / max(rec.dph, 1e-6) * 3600)
                    # Ten minutes for the changeover -- enough for the next pass
                    # to connect, not enough to cost anything noticeable.
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
                # The live machine, not the last one seen: `state["iid"]` is not
                # cleared after a destruction, and the next pass would wait out
                # the attempt ceiling on a destroyed one. An instance stays alive
                # exactly under `--keep`; one that failed to be destroyed is alive
                # too but must not be reused.
                report["instance_id"] = iid if (keep and iid) else None
                report["dph"] = rec.dph
                report["cost_usd"] = rec.cost_usd
            # The last thing in this `finally` may not be the first that throws:
            # `ledger.append` writes a file, and a raise from here costs the money
            # record of the run, the summary line below and the signal restore at
            # once -- the very failure the signal machinery exists to prevent.
            try:
                ledger.append(rec)
            except Exception as e:
                log(f"WARNING: the run could NOT be written to the ledger ({e}) "
                    f"-- the money below is real and was not recorded. The run "
                    f"itself is finished; it is the record that failed")
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
        finally:
            _restore_signals(old_signals)
