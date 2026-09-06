"""Rental deadlines: two ceilings, each of which binned GOOD machines.

THERE WERE NO CHECKS ON `remote/` AT ALL, and neither defect below was found
by reading the code. Both came out of a PAID RUN on 3 September 2026: three
good machines binned in a row, $0.081 and 13 minutes out of 60 before it was
stopped by hand.

THE PROBE COULD NOT KEEP UP WITH ITS OWN FLOOR. The rejection floor in
`runner` follows our own channel (`min(limit, 0.5*ours)`), while the probe's
deadline was wired in: 4 MB in 25 s. At the floor of 0.90 Mbit/s seen that
evening, `ours` was 1.8; 32 megabits take 18 s at best and do not fit into 25
with the ssh handshake. The probe returned 0 -- a "timeout" no different from
a dead machine.

`remote/box.py` recounts the same evening with `ours` at 2.8 and the floor at
1.42. Both cannot describe one attempt, and neither can be checked: until the
fix beside `test_the_channel_that_decides_reaches_the_ledger`, our own
downlink was measured on every rental and written down nowhere. It is a ledger
field now, so the next run settles it instead of the next argument.

A CEILING INSIDE A CEILING. Container start was cut by `min(BOOT_LIMIT_S,
remaining)` = `min(120, 480)` = 120 s. Machine 49873851 was pulling the image
fine ("Download complete", "Pull complete") and was cut off at 2:12 with 360 s
of the attempt budget unspent.

Both are one defect by make: a quantity that MUST be derived from another was
written down as a number. The checks below demand the derivation.
"""
import ast
import inspect
import time

import support

from booksmith.remote import box as rbox
from booksmith.remote import ledger
from booksmith.remote import runner


class _FakeSsh(rbox.Box):
    """A box that never goes over ssh: no real channel is measured here."""

    def __init__(self):
        self.seen = None

    _ssh = ["ssh"]
    _addr = "root@nowhere"


class _Stream:
    """A pipe handing out bytes at a set rate. Stands in for ssh."""

    def __init__(self, mbps, total=None, clock=None):
        self.mbps = mbps
        self.clock = clock if clock is not None else [0.0]
        self.total, self.sent = total, 0
        self.stdout = self

    # How much virtual time one `read` costs. A pipe hands over what has
    # ARRIVED, not what was asked for, and that difference is the whole reason
    # the probe reads for a time rather than for a size.
    QUANTUM = 0.01

    def read(self, n):
        # ON A CLOCK OF OUR OWN, and that is the whole point. This used to read
        # `time.time()` and sleep 10 ms when nothing had arrived yet, so the
        # measurement rode the scheduler: under a stall the probe's elapsed
        # time grew while no bytes flowed, and the check failed about 1.4 % of
        # runs -- a defect of the check, not of the probe.
        #
        # The first virtual-clock edition then handed over the WHOLE request
        # and charged the clock for it, so one 64 KiB read at 62 kbit/s cost
        # 8.5 virtual seconds and the probe could not be seen to overrun its
        # deadline at all. A pipe gives what a quantum of time delivered.
        if self.total is not None and self.sent >= self.total:
            return b""              # the stream is over
        give = int(self.mbps * 1e6 / 8 * self.QUANTUM)
        give = min(n, give) if self.total is None else min(
            n, give, self.total - self.sent)
        self.clock[0] += self.QUANTUM
        self.sent += give
        return b"\x00" * give

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _probe_at(mbps, seconds=0.6, total=None):
    """Run the real `Box.probe` against a pipe of a given rate.

    The pipe and the probe share ONE virtual clock, so the answer depends on
    the probe's arithmetic and on nothing else -- not on the scheduler, not on
    how long this machine takes to run a loop.
    """
    return _probe_timed(mbps, seconds, total)[0]


class _Clock:
    """A stand-in for the `time` module, seen only by `remote.box`.

    NOT `time.time = ...`. The first edition assigned through `rbox.time`,
    which IS the stdlib module, so the patch was process-wide for the length
    of the probe -- in a project that runs heartbeat threads. Replacing the
    NAME in one module's namespace reaches only the code under test.
    """

    def __init__(self, at):
        self.at = at

    def time(self):
        return self.at[0]


def _probe_timed(mbps, seconds=0.6, total=None):
    """(measured Mbit/s, virtual seconds, the argv the probe actually ran)."""
    import subprocess
    clock = [1000.0]
    stream = _Stream(mbps, total, clock)
    ran = []
    was_popen, was_time = subprocess.Popen, rbox.time

    def spy(cmd, *a, **k):
        ran.append(cmd)
        return stream

    subprocess.Popen = spy
    rbox.time = _Clock(clock)
    try:
        got = _FakeSsh().probe(seconds=seconds)
        return got, clock[0] - 1000.0, (ran[0] if ran else None)
    finally:
        subprocess.Popen = was_popen
        rbox.time = was_time


def test_a_narrow_channel_is_measured_not_called_broken():
    """A narrow channel gives a SMALL NUMBER, not a zero.

    The probe used to demand exactly 4 MB and wait 25 s for them; short of
    that it returned 0.0, and a zero in `runner` means "the machine is
    broken" -- "we failed to receive" written down as "it cannot send",
    indistinguishable BY CONSTRUCTION. Can fail: bring back the count of "did
    exactly mb megabytes arrive".

    IT USED TO BE THE FLAKY CHECK OF THIS FILE, about 1.4 % of calls, and the
    defect was in the check: the stub rode the real clock and slept 10 ms when
    nothing had arrived, so a scheduler stall grew the probe's elapsed time
    while no bytes flowed. Pipe and probe now share one virtual clock, and the
    answer depends on the probe's arithmetic alone.
    """
    narrow = _probe_at(1.16)
    # A BAND OF 0.5..3.0 LET A DOUBLING THROUGH: 1.16 read as 2.32 fits it,
    # and 2.32 clears the default rejection floor of 2.0 -- a machine too slow
    # to use, accepted. Under a virtual clock the probe's arithmetic is exact,
    # so the band is what exactness allows and not what a scheduler forced.
    assert 1.10 <= narrow <= 1.25, (
        f"a 1.16 Mbit/s channel measured as {narrow:.2f} -- under a clock "
        f"this probe controls, the arithmetic is exact, and anything else is "
        f"the arithmetic being wrong")
    assert narrow > 0.5, (
        f"a 1.16 Mbit/s channel measured as {narrow:.2f} -- the probe "
        f"again confuses \"we are slow\" with \"the machine is broken\"")
    assert narrow < 3.0, (
        f"measured {narrow:.2f} instead of ~1.16 -- the probe lies upward")


def test_a_broken_machine_still_gives_a_number_below_any_floor():
    """A broken machine gives 0.06, not zero -- and is binned anyway.

    The probe was written for a machine at 62 kbit/s that took 3.5 MB in
    seven and a half minutes. Making it honest made it easy to make it blind:
    here it RUNS against such a pipe and must return a number BELOW the floor.
    """
    broken = _probe_at(0.062)
    assert 0.055 <= broken <= 0.070, (
        f"a 62 kbit/s machine measured as {broken:.4f} -- exact arithmetic "
        f"over an exact clock must give back what was put in")
    assert broken < 0.3, (
        f"a 62 kbit/s machine measured as {broken:.2f} Mbit/s -- the probe "
        f"no longer tells a broken one from a slow one")
    healthy = _probe_at(50.0)
    assert 47.0 <= healthy <= 53.0, (
        f"a 50 Mbit/s machine measured as {healthy:.1f} -- exact in, exact "
        f"out, or the arithmetic is wrong")
    assert healthy > 10.0, (
        f"a healthy machine measured as {healthy:.1f} Mbit/s -- the probe "
        f"reads low")


def test_the_probe_stops_ON_TIME_and_not_on_a_byte_count():
    """It reads FOR A TIME. Reading for a SIZE is the defect it was born from.

    The original probe demanded exactly 4 MB and returned 0.0 short of them,
    so a slow machine was written down as a broken one. Under a virtual clock
    the RATE alone cannot tell the two loops apart -- `while got < 4 MB` and
    `while elapsed < seconds` both divide the same bytes by the same time --
    so what is measured here is the DEADLINE: a 62 kbit/s pipe needs 516
    seconds to hand over 4 MB and must be let go after the 0.6 it was given.

    Without this, a size demand passed every check in the file.
    """
    # ONE READ MAY STRADDLE THE DEADLINE and that is lawful: the loop checks
    # the clock, then reads, and the read takes time. TWO is a `do-while`
    # dressed as a deadline, and on a real twelve-second probe over a slow
    # link one chunk can be many seconds. The band is therefore one quantum
    # either side, not the fourfold slack it began with -- ten chunks past the
    # end passed that.
    slack = _Stream.QUANTUM
    for mbps in (0.062, 1.16, 50.0):
        _, took, _cmd = _probe_timed(mbps, seconds=0.6)
        assert took <= 0.6 + 2 * slack, (
            f"at {mbps} Mbit/s the probe ran {took:.3f} s of the 0.6 it was "
            f"given -- it is waiting for a SIZE, and a slow machine will be "
            f"written down as a broken one, which is the defect this probe "
            f"was written to end")
        assert took >= 0.6 - slack, (
            f"at {mbps} Mbit/s the probe gave up after {took:.3f} s of 0.6 -- "
            f"it stopped on a byte count, and one early chunk is the TCP "
            f"ramp-up, not the channel")


def test_the_probe_asks_THE_MACHINE_and_asks_it_for_a_bounded_stream():
    """It must contact the box, over ssh, for `mb_cap` of random bytes.

    `subprocess.Popen` is replaced wholesale by the stub, so nothing looked at
    the command it was given -- and a probe reading OUR OWN `/dev/urandom`
    passed every check in this file, reporting hundreds of Mbit/s for every
    machine. The 62 kbit/s machine the whole apparatus exists for would have
    sailed through. "Measured the link" and "measured nothing" were the same
    to the suite.

    `mb_cap` is checked too: it appears only inside the command string, so it
    was untested by construction, and without it the probe asks for an endless
    stream from a machine that is billing.
    """
    _, _, cmd = _probe_timed(50.0, seconds=0.6)
    assert cmd is not None, "the probe started no process at all"
    argv = cmd if isinstance(cmd, list) else [cmd]
    joined = " ".join(str(x) for x in argv)
    assert argv[0] == "ssh" and _FakeSsh._addr in argv, (
        f"the probe did not go to the machine over ssh: {argv}. It measured "
        f"something, and the something was not the link")
    assert "/dev/urandom" in joined, (
        f"the probe asks for something other than random bytes: {joined}. "
        f"Zeros compress in ssh and give a pretty lie")
    assert "head -c" in joined, (
        f"the probe asks for an UNBOUNDED stream: {joined}. `mb_cap` is the "
        f"only thing stopping a machine that is billing from sending forever")


def test_the_probe_divides_by_the_time_it_actually_took():
    """A stream that ends early is measured over the time it USED.

    Dividing by the constant `seconds` instead of the measured span passed
    every check, because `total` was used at exactly one value in this file --
    zero -- where both arithmetics give 0.0. A machine whose ssh dies after a
    third of the budget, having delivered its bytes at full speed, must read
    at full speed and not at a third of it.
    """
    mbps, seconds = 30.0, 0.6
    bytes_in_a_third = int(mbps * 1e6 / 8 * (seconds / 3))
    got, took, _ = _probe_timed(mbps, seconds=seconds, total=bytes_in_a_third)
    assert took < 0.9 * seconds, (
        f"the stream ended after a third and the probe still ran {took:.2f} "
        f"of {seconds} s -- it is not noticing the end of the stream")
    assert 0.7 * mbps <= got <= 1.4 * mbps, (
        f"a stream that ended early measured {got:.1f} against {mbps} -- the "
        f"probe divides by the budget it was given, not by the time it used, "
        f"so every early end reads as a slow machine")


def test_a_dead_channel_is_the_only_zero():
    """Zero is left to exactly one case: NOT ONE BYTE arrived.

    That is the one thing `runner` may answer "take another" to without
    doubting.
    """
    assert _probe_at(0.0, total=0) == 0.0, "a dead pipe gave a non-zero"


class _FakeVast:
    """A rental that rents nothing: only the deadline passed in is caught."""

    def __init__(self):
        self.boot_timeout = None

    def wait_running(self, iid, timeout):
        self.boot_timeout = timeout
        raise RuntimeError("no further: the deadline is caught")

    def attach_key(self, *a):
        pass


def test_connect_gives_the_boot_the_whole_attempt():
    """An attempt has ONE deadline. No second ceiling lives inside it.

    `min(BOOT_LIMIT_S, remaining)` cut the boot at 120 s out of a 480 s
    attempt budget -- the machine it killed is named above.

    BY BEHAVIOUR, NOT BY PARSING THE SOURCE: the first edition read the text
    of the function through `inspect.getsource`, and a mutation that rebuilds
    the module in memory was invisible to it -- the battery declared it caught
    having checked nothing. What is caught is what reaches `wait_running`.
    """
    v = _FakeVast()
    try:
        runner.connect(v, 1, None, None, attempt_limit=480.0)
    except RuntimeError:
        pass
    assert v.boot_timeout is not None, "wait_running was never called"
    assert v.boot_timeout > 400.0, (
        f"the boot got {v.boot_timeout:.0f} s of 480 -- a ceiling of its "
        f"own is back inside the attempt, and it already rejected "
        f"machines pulling the image fine")
    assert "boot_limit" not in inspect.signature(runner.connect).parameters, (
        "a separate ceiling on the container boot is back in connect")
    assert not hasattr(runner, "BOOT_LIMIT_S"), (
        "BOOT_LIMIT_S is back in the module: it limited nothing but "
        "usable machines")


def _blame_with(link, best, ours, limit=None):
    """Call the REAL guard, directly, not by digging its body out of source.

    The first edition pulled `_blame` out of `_rent` with `ast` and ran it in
    a fake environment, the guard being locked in a closure -- so it checked
    TEXT, and the battery honestly said NOT CAUGHT on both mutations, which
    rebuild the module in memory. The guard lives at module level now, and
    nothing is left to check but behaviour. `limit` is absent from the
    signature, and that is checked too.
    """
    recorded = []
    runner.blame_machine({"machine_id": 777}, "trial", ours=ours, link=link,
                         best_link=best,
                         mark=lambda mid, why: recorded.append((mid, why)),
                         say=lambda *a: None)
    return recorded


def test_a_machine_is_blamed_only_with_a_witness():
    """Onto the PERMANENT list only when another machine gave three times as
    much.

    What it cost (3 September 2026): the guard compared our HTTP channel with
    the floor (`ours < 2*limit`) while the probe measures ssh. Our gap between
    transports is tenfold -- HTTP 4.6 and 2.4 against ssh 0.34 and 0.25 from
    TWO DIFFERENT machines in a row -- both listed for nothing.
    """
    assert _blame_with(link=0.25, best=0.34, ours=4.6) == [], (
        "machine listed FOREVER although the best one seen gave only 0.34 "
        "against its 0.25 -- no witness that the machine is at fault")
    assert _blame_with(link=0.25, best=7.0, ours=4.6), (
        "machine NOT listed although another over the same ssh gave 7.0 "
        "against its 0.25 -- this is exactly the machine's fault")
    assert _blame_with(link=0.25, best=7.0, ours=0.0) == [], (
        "listed while our own channel was not measured")

    # ABOVE THE WITNESS FLOOR, so the RATIO is what decides here and nothing
    # else. Without this pair the floor answers both cases and the ratio can
    # be deleted unnoticed -- which is exactly what happened when the floor
    # was added: two mutations over `best_link < 3 * link` stopped being
    # caught, because 0.34 never reached the ratio at all.
    assert _blame_with(link=2.0, best=3.0, ours=4.6) == [], (
        "machine listed FOREVER on 2.0 Mbit/s while the best seen was 3.0 -- "
        "a witness must be three times better, not merely better")
    assert _blame_with(link=2.0, best=9.0, ours=4.6), (
        "machine NOT listed on 2.0 Mbit/s against a witness of 9.0 -- the "
        "ratio has stopped deciding anything")


def _loop(links, ours=4.6):
    """Replay `_rent`'s blame path over a sequence of probe readings.

    `best_link` is raised BEFORE the machine is judged, exactly as `_rent`
    does it, so what comes out is what the real loop would do.
    """
    best, banned = 0.0, []
    for i, link in enumerate(links):
        best = max(best, link)
        if _blame_with(link=link, best=best, ours=ours):
            banned.append(i)
    return banned


def test_the_permanent_list_is_reachable_at_the_default_floor():
    """A guard that can never fire is not a guard, and this one could not.

    The witness floor was first set to 2.0 -- the same number as the default
    `MIN_LINK_MBPS`. A machine only reaches `blame_machine` after being
    REJECTED, so every reading in `best_link` is below the rejection floor:
    `best_link < floor <= limit`. With the two equal, the first gate was true
    every time and NOTHING could be blacklisted, including the 62 kbit/s
    machine `_rent`'s own comment says the list was made for. Swept over 2744
    three-probe sequences at the default: zero blacklistings.

    So the two numbers must not meet, and this says so with a machine the
    loop can actually produce: one at 1.5 Mbit/s -- under the floor of 2.0,
    hence rejected, hence a witness -- and one at 0.1 after it.
    """
    from booksmith.run import knobs
    floor = float(knobs.KNOB["MIN_LINK_MBPS"].default)
    assert runner.WITNESS_MBPS < floor, (
        f"the witness floor {runner.WITNESS_MBPS} has reached the rejection "
        f"floor {floor}. Every witness is a REJECTED machine, so its reading "
        f"is below the rejection floor by construction -- the permanent list "
        f"can then never fire at all")
    assert _loop([1.5, 0.1]) == [1], (
        f"a machine reading 0.1 Mbit/s beside one that managed 1.5 was NOT "
        f"blacklisted: at the default floor of {floor} both are rejected, so "
        f"this is the only shape a witness can take, and the list is empty "
        f"without it")


def test_a_path_dying_at_our_end_blames_nobody_at_all():
    """The whole rent loop, not one call: a sick path bans NO machine.

    Requiring a witness above zero closed exactly one input -- `best_link ==
    0.0` -- and a probe that receives ONE BYTE in twelve seconds returns
    6.7e-07, not zero. Replayed over five machines, a path leaking a single
    64 KiB chunk to the first of them banned the other four FOREVER, and this
    project has no command that takes an entry off that list.

    So the witness has a floor of its own, and this drives the three shapes a
    sick path takes: one machine leaks a chunk, one leaks a byte, and all of
    them dribble.
    """
    for name, links in (
            ("one 64 KiB chunk", [0.0437, 0.0, 0.0, 0.0, 0.0]),
            ("one byte in twelve seconds", [6.67e-07, 0.0, 0.0, 0.0, 0.0]),
            ("every machine dribbles", [0.050, 0.008, 0.012, 0.006, 0.009]),
            ("only 62 kbit/s machines", [0.0, 0.0, 0.062, 0.0, 0.062])):
        banned = _loop(links)
        best = max(links)
        assert not banned, (
            f"{name}: machines {banned} went onto the PERMANENT list while "
            f"the best anyone gave us was {best:.4g} Mbit/s -- that is our "
            f"path, not theirs, and the list has no undo")

    # And a healthy path still condemns: one good machine, then a bad one.
    best = max(0.0, 7.0)
    assert _blame_with(link=0.25, best=best, ours=4.6), (
        "with a witness at 7.0 Mbit/s a machine giving 0.25 was NOT listed -- "
        "the floor has swallowed the rule it was added to")


def test_a_path_that_sagged_mid_loop_condemns_nobody():
    """`best_link` is a maximum and never decays, so a witness goes stale.

    Replayed at a raised rejection floor: one machine at 7 Mbit/s, then four
    reading 2.0-2.3 -- all four onto the PERMANENT list, because the 7 was
    recorded before our own path sagged and nothing said it had. The guard
    re-measures our downlink at the moment of blaming, which turns that
    inference into a measurement.
    """
    recorded = []
    got = runner.blame_machine({"machine_id": 9}, "trial", ours=20.0,
                               ours_now=3.0, link=2.2, best_link=7.0,
                               mark=lambda mid, why: recorded.append(mid),
                               say=lambda *a: None)
    assert got is False and not recorded, (
        "a machine was listed FOREVER on a contrast with a witness measured "
        "while our own path was six times faster than it is now")

    assert runner.blame_machine({"machine_id": 9}, "trial", ours=20.0,
                                ours_now=19.0, link=2.2, best_link=7.0,
                                mark=lambda *a: None, say=lambda *a: None), (
        "our path was steady and the machine still escaped: the sag guard "
        "has swallowed the rule it was added beside")


def test_a_zero_probe_with_no_witness_at_all_blames_nobody():
    """The commonest zero, and the one the arithmetic used to let through.

    `best_link < 3 * link` reads `0.0 < 0.0` at a zero probe -- False -- so the
    machine went onto the PERMANENT list with nothing to compare it against.
    That is the shape of a dead path at OUR end: the probe measures by time, so
    every machine returns zero, and every one of them would have been banned
    forever, starting with the first.

    Both directions, because only one of them was ever wrong: a zero with no
    witness blames nobody, and a zero beside a machine that DID deliver is the
    machine's fault and must still be listed.
    """
    assert _blame_with(link=0.0, best=0.0, ours=4.6) == [], (
        "machine listed FOREVER on a zero probe while NO machine had yet "
        "given us anything over ssh -- there is no witness at all, and this "
        "is how a dead path at our end bans the whole market")
    assert _blame_with(link=0.0, best=5.0, ours=4.6), (
        "machine NOT listed on a zero probe although another gave 5.0 over "
        "the same ssh -- that witness is exactly what the list is for")


def test_a_failed_blacklist_write_does_not_kill_the_rental():
    """Failing to WRITE DOWN a ban may not abandon a running machine.

    `mark_bad` writes a file, and a file write can fail -- a read-only ledger
    directory took the whole rental with a `PermissionError` out of the middle
    of `_rent`, machine taken and billing. The OTHER caller of `mark_bad`, the
    CUDA branch, has always been wrapped; the money-path one was not.
    """
    said = []

    def refuses(mid, why):
        raise PermissionError("[Errno 13] the ledger directory is read-only")

    got = runner.blame_machine({"machine_id": 5}, "trial", ours=4.6, link=0.1,
                               best_link=9.0, mark=refuses, say=said.append)
    assert got is False, "a failed write was reported as a successful ban"
    assert any("could NOT be written" in line for line in said), (
        f"the failure to record the ban was swallowed: {said}")


def test_no_write_in_the_cleanup_can_leave_ctrl_c_dead():
    """`run_job` restores the signal handlers WHATEVER happens in its cleanup.

    `ledger.append(rec)` stood unwrapped at the end of that block, and a
    read-only ledger directory raised `PermissionError` from it. Three things
    went at once: the money record of the run, the summary line, and
    `_restore_signals` -- so SIGINT and SIGTERM were left at `SIG_IGN` and
    Ctrl-C was DEAD for the rest of the process. That is the exact failure the
    signal machinery exists to prevent, caused by the cleanup that installs it.

    WHAT IS ASKED IS THE STRUCTURE, not a list of calls that might throw.
    Naming the risky ones is guesswork and goes stale the day another is
    added; `_restore_signals` being the `finally` of its own block is a
    property that holds for whatever is written above it.
    """
    tree = support.tree("remote/runner.py")
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_job")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_restore_signals"]
    assert calls, "run_job no longer restores the signal handlers at all"

    protected = []
    for t in ast.walk(fn):
        if not (isinstance(t, ast.Try) and t.finalbody):
            continue
        protected += [c for stmt in t.finalbody for c in ast.walk(stmt)
                      if isinstance(c, ast.Call)
                      and isinstance(c.func, ast.Name)
                      and c.func.id == "_restore_signals"]
    # The dry-run path returns early and never ignores the signals; the one
    # that matters is the cleanup, and it must be a `finally`.
    assert protected, (
        "`_restore_signals` is not in a `finally` at all: anything that "
        "throws in the cleanup leaves SIGINT and SIGTERM ignored, and Ctrl-C "
        "dead for the rest of the process")

    ignore = next(n for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_ignore_signals")
    guard = next((t for t in ast.walk(fn)
                  if isinstance(t, ast.Try) and t.finalbody
                  and any(c in ast.walk(stmt) for stmt in t.finalbody
                          for c in [ignore])), None)
    assert guard is not None, (
        "the block that IGNORES the signals is not the block that restores "
        "them: a throw between the two leaves them ignored")


def test_a_floor_that_is_not_a_number_is_refused_before_any_money():
    """`nan` compares False with everything, and that cost five rentals.

    `float("nan")` is a legal float, so `MIN_LINK_MBPS=nan` passed the
    registry and made `link >= floor` and `link < floor` BOTH false: every
    machine fell through every branch to "the reason was not named", five
    rentals paid for and not one of them accepted or blamed. A typo that
    costs money must refuse before the first rental.
    """
    import os
    was = os.environ.get("MIN_LINK_MBPS")
    for bad in ("nan", "inf", "-1", "narrow"):
        os.environ["MIN_LINK_MBPS"] = bad
        try:
            runner._min_link_mbps()
        except SystemExit as e:
            assert "MIN_LINK_MBPS" in str(e), e
        else:
            raise AssertionError(
                f"MIN_LINK_MBPS={bad!r} was accepted as a rejection floor")
        finally:
            if was is None:
                os.environ.pop("MIN_LINK_MBPS", None)
            else:
                os.environ["MIN_LINK_MBPS"] = was
    assert runner._min_link_mbps() >= 0, "the real floor stopped working"


def test_both_journal_writers_survive_a_bare_file_name():
    """`BOOKSMITH_LEDGER` may be a bare name, and both writers must cope.

    `os.path.dirname("bad-machines.json")` is `""`, and `os.makedirs("")`
    raises `FileNotFoundError`. `append` guarded with `or "."` and `mark_bad`
    did not -- two copies of one line, one of them right. The unguarded one
    runs from the MIDDLE of `_rent`, with the machine taken and billing, on
    the path that blacklists a machine.

    Both are called here, not read: a check that greps for `or "."` would pass
    on a third copy written a fourth way.
    """
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    was = os.getcwd()
    os.chdir(tmp)
    try:
        ledger.mark_bad(4242, "trial", path="bad-machines.json")
        assert os.path.isfile(os.path.join(tmp, "bad-machines.json")), (
            "mark_bad wrote nothing where a bare file name was given")
        ledger.append(ledger.Run(job="trial", image="none", gpu="none"),
                      path="ledger.jsonl")
        assert os.path.isfile(os.path.join(tmp, "ledger.jsonl")), (
            "append wrote nothing where a bare file name was given")
    finally:
        os.chdir(was)


def test_the_channel_that_decides_reaches_the_ledger():
    """`ours` sets the floor and gates the blacklist, so it must be recorded.

    It was not. The only record of it was prose, and the prose disagreed with
    itself about the same evening -- 1.8 Mbit/s in the header of this file
    against 2.8 in `remote/box.py`, both about 3 September 2026 -- while the
    119 rows of the ledger could not settle it, because the quantity was never
    written down. A number that decides a PERMANENT ban and lives only in a
    comment is the "log the quantity" rule broken at the source.

    DRIVEN, NOT DECLARED. The first edition of this check asked the dataclass
    whether it had the field; deleting the line in `_rent` that FILLS it left
    every check in the project green. A field nobody writes is the same
    silence in a different place, so `_rent` is run -- against a rental that
    refuses at once -- and the record is read afterwards.
    """
    from dataclasses import asdict
    row = asdict(ledger.Run(job="t", image="i", gpu="g"))
    assert "our_downlink_mbps" in row, (
        f"the ledger row does not carry our own downlink: {sorted(row)}")
    assert row["our_downlink_mbps"] is None, (
        "the default is not None -- NOT MEASURED would be written as 0.0, and "
        "0.0 is what makes `blame_machine` refuse to act")

    rec = ledger.Run(job="t", image="i", gpu="g")
    was = runner._our_downlink_mbps
    runner._our_downlink_mbps = lambda *a, **k: 3.25
    try:
        runner._rent(_RefusingVast(), _spec(), None, {}, rec, [], time.time())
    except BaseException:                                   # noqa: BLE001
        pass                          # the rental refuses; the record is why
    finally:
        runner._our_downlink_mbps = was
    assert rec.our_downlink_mbps == 3.25, (
        f"`_rent` measured our downlink and did not write it down: "
        f"{rec.our_downlink_mbps!r}. It decides the rejection floor and gates "
        f"a permanent ban, and the ledger would say nothing about it")


class _RefusingVast:
    """A rental that offers nothing: `_rent` gives up before touching money."""

    def offers(self, *a, **k):
        return []

    def show_instances(self):
        return []


def _spec():
    from booksmith.remote.spec import JobSpec
    return JobSpec(name="trial", image="none", command="true")


def test_the_verdict_cannot_depend_on_the_rejection_floor():
    """The rejection floor takes NO part in the permanent-list verdict.

    The guard used to look at `limit`, and lowering the floor from 2.0 to 0.4
    turned a ban into a pass: one knob doing two opposite jobs. It is gone
    from the signature entirely, which is the firmest form of the ban.
    """
    import inspect
    names = set(inspect.signature(runner.blame_machine).parameters)
    assert "limit" not in names and "floor" not in names, (
        f"the floor is back in the permanent-list guard: {sorted(names)}. "
        f"Loosening it to let machines through would make banning easier")


class _FakeVastApi:
    """A vast wrapper that always refuses and counts the calls."""

    def __init__(self, err):
        self.err, self.calls = err, 0

    def destroy_instance(self, id):
        self.calls += 1
        raise RuntimeError(self.err)

    def show_instances(self):
        self.calls += 1
        raise RuntimeError(self.err)


def test_destroy_backs_off_instead_of_hammering():
    """The pauses GROW, and their sum stays under the dead man's grace.

    What it cost (3 September 2026): a flat 4 s pause over five attempts
    stood here, and each attempt makes TWO API calls -- destroy plus check.
    Ten requests in twenty seconds. When vast.ai began answering 403 the code
    kept hammering at the same rate, and the key stopped opening ANYTHING,
    `/users/current` included (checked with `curl` on the same key: the
    refusal came from them, not from our wrapper).

    The sum must be LESS than the dead man's grace: if destruction fails
    outright the machine puts itself out, and stretching the attempts past
    that grace is paying to wait for nothing.
    """
    from booksmith.remote.vast import Vast
    steps = list(Vast.RETRY_S)
    assert steps == sorted(steps) and steps[-1] > steps[0] * 4, (
        f"the backoffs do not grow: {steps}. A refusal by rate must not be "
        f"answered at the same rate")
    assert sum(steps) < 900, (
        f"the backoffs sum to {sum(steps)} s, not under the dead man's "
        f"grace (900 s) -- we wait longer than the machine lives alone")


def test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine():
    """403 and 429 are A REFUSAL OF ACCESS, not "the machine disobeyed".

    Different troubles: "destruction did not work" is cured by a retry, "we
    are not being let in" is made worse by one. And the `alive` check that
    follows then answers "alive" only because there is nobody to ask -- the
    absence of an observation, not an observation.
    """
    import time as _t

    from booksmith.remote import vast as vmod

    was_sleep, was_log = _t.sleep, vmod.log
    stated = []
    v = vmod.Vast.__new__(vmod.Vast)
    v.v = _FakeVastApi("403 Client Error: Forbidden")
    _t.sleep = lambda s: None
    vmod.log = stated.append
    try:
        assert v.destroy(1) is False
    finally:
        _t.sleep, vmod.log = was_sleep, was_log
    everything = "\n".join(stated)
    assert "REFUSAL OF ACCESS" in everything, (
        f"403 named as an ordinary destroy failure:\n{everything[:400]}")
    assert "nobody to ask" in everything, (
        '"alive" after a refusal of access is passed off as an observation')


class _BoxThatFailsAfterPulse:
    """A machine whose pulse started and whose link then broke.

    Exactly the case that left an abandoned machine immortal: the pulse
    starts BEFORE the first network command, and that command fails normally.
    """

    declared: list = []

    def __init__(self, *a, **kw):
        self.pulse = False
        _BoxThatFailsAfterPulse.declared.append(self)

    def wait_ready(self, **kw):
        pass

    def start_heartbeat(self):
        self.pulse = True

    def stop_heartbeat(self):
        self.pulse = False

    def check_deadman(self):
        raise OSError("ssh went silent right after the pulse")


def test_a_failed_connect_leaves_no_machine_with_a_live_pulse():
    """A failure AFTER `start_heartbeat` must put the pulse out.

    WHAT THIS COST. `connect` starts the pulse and then goes to the network
    (`check_deadman`), where a failure is normal. Before the repair the `box`
    never reached the caller -- the variable in `_rent` stayed UNBOUND,
    `stop_heartbeat` raised `UnboundLocalError`, and a silent
    `except Exception: pass` swallowed it. The machine went to `undead` WITH A
    LIVE PULSE: our thread kept touching `/root/.alive` every 30 s to the end
    of the run, switching OFF the dead man's watch -- the only one of the four
    ways of putting a machine out that depends neither on our key nor on our
    process. On a second attempt the pulse put out would be the PREVIOUS
    machine's. And not one line went to the log.
    """
    _BoxThatFailsAfterPulse.declared = []
    was = runner.Box
    runner.Box = _BoxThatFailsAfterPulse
    try:
        for iid in (1001, 1002):
            try:
                runner.connect(_FakeVastReady(), iid, _SpecStub(), None,
                               attempt_limit=60.0)
            except OSError:
                pass
    finally:
        runner.Box = was

    declared_n = _BoxThatFailsAfterPulse.declared
    assert len(declared_n) == 2, (
        f"the stub machine was made {len(declared_n)} times instead of two "
        f"-- the check never reached the place it guards")
    live = [i for i, b in enumerate(declared_n, 1) if b.pulse]
    assert not live, (
        f"after the link failed the pulse stayed alive on machines {live}. "
        f"Our thread would revive an abandoned machine all run, its "
        f"dead-man's watch off -- whoever started it must stop it")


class _FakeVastReady:
    """A rental that reaches ssh and no further: the trouble is in `Box`."""

    def wait_running(self, iid, timeout):
        pass

    def ssh_target(self, iid):
        return ("root", "10.0.0.1", 22)

    def attach_key(self, *a):
        pass


class _SpecStub:
    workdir = "/workdir"
