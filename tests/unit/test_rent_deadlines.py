"""Rental deadlines: two ceilings, each of which binned good machines.

Both are one defect by make: a quantity that must be derived from another was
written down as a number. The probe's deadline was wired in while the rejection
floor follows our own channel, so a slow but usable machine timed out; and
container start was cut by `min(BOOT_LIMIT_S, remaining)`, cutting off a machine
that was pulling its image fine with most of the attempt budget unspent.

The checks below demand the derivation.
"""
import inspect
import time

import pytest

from booksmith.core.errors import Refusal

pytest.importorskip("vastai")          # the `remote` extra
from booksmith.remote import box as rbox
from booksmith.remote import ledger
from booksmith.remote import runner
import support


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

    # How much virtual time one `read` costs. A pipe hands over what has arrived,
    # not what was asked for, which is why the probe reads for a time.
    QUANTUM = 0.01

    def read(self, n):
        # On a clock of our own: the real clock makes the measurement ride the
        # scheduler, and handing over a whole request in one read would charge
        # the clock for bytes a quantum never delivered.
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
    """Run the real `Box.probe` against a pipe of a given rate. The pipe and the
    probe share one virtual clock, so the answer depends on the probe's
    arithmetic and on nothing else."""
    return _probe_timed(mbps, seconds, total)[0]


class _Clock:
    """A stand-in for the `time` module, seen only by `remote.box`. The name is
    replaced in one module's namespace, not `time.time` itself, which would
    patch the whole process for the length of the probe."""

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
    """A narrow channel gives a small number, not a zero: a zero in `runner`
    means "the machine is broken", so "we failed to receive" written down as "it
    cannot send" is indistinguishable by construction."""
    narrow = _probe_at(1.16)
    # A band of 0.5..3.0 would let a doubling through: 1.16 read as 2.32 clears
    # the default rejection floor of 2.0. Under a virtual clock the arithmetic is
    # exact, so the band is what exactness allows.
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
    """A broken machine gives 0.06, not zero -- and is binned anyway: the probe
    runs against such a pipe and must return a number below the floor."""
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
    """It reads for a time; reading for a size is the defect it was born from.
    The rate alone cannot tell the two loops apart, so what is measured here is
    the deadline: a 62 kbit/s pipe is let go after the 0.6 it was given."""
    # One read may straddle the deadline and that is lawful: the loop checks the
    # clock, then reads, and the read takes time. Two is a `do-while` dressed as
    # a deadline, so the band is one quantum either side.
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
    """It must contact the box, over ssh, for `mb_cap` of random bytes: with
    `Popen` replaced wholesale, a probe reading our own `/dev/urandom` would
    report hundreds of Mbit/s for every machine. `mb_cap` is checked too."""
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
    """A stream that ends early is measured over the time it used: a machine whose
    ssh dies after a third of the budget, having delivered its bytes at full
    speed, must read at full speed and not at a third of it."""
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
    """Zero is left to exactly one case: not one byte arrived. That is the one
    thing `runner` may answer "take another" to without doubting."""
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


def _blame_with(link, best, ours, limit=None):
    """Call the real guard directly. It lives at module level, so nothing is left
    to check but behaviour; `limit` is absent from the signature, and that is
    checked too."""
    recorded = []
    runner.blame_machine({"machine_id": 777}, "trial", ours=ours, link=link,
                         best_link=best,
                         mark=lambda mid, why: recorded.append((mid, why)),
                         say=lambda *a: None)
    return recorded


def test_a_machine_is_blamed_only_with_a_witness():
    """Onto the permanent list only when another machine gave three times as
    much: the guard compares ssh with ssh, since our gap between transports is
    tenfold and the HTTP channel against the floor lists a machine for nothing."""
    assert _blame_with(link=0.25, best=0.34, ours=4.6) == [], (
        "machine listed FOREVER although the best one seen gave only 0.34 "
        "against its 0.25 -- no witness that the machine is at fault")
    assert _blame_with(link=0.25, best=7.0, ours=4.6), (
        "machine NOT listed although another over the same ssh gave 7.0 "
        "against its 0.25 -- this is exactly the machine's fault")
    assert _blame_with(link=0.25, best=7.0, ours=0.0) == [], (
        "listed while our own channel was not measured")

    # Above the witness floor, so the ratio is what decides here and nothing
    # else: without this pair the floor answers both cases and the ratio could
    # be deleted unnoticed.
    assert _blame_with(link=2.0, best=3.0, ours=4.6) == [], (
        "machine listed FOREVER on 2.0 Mbit/s while the best seen was 3.0 -- "
        "a witness must be three times better, not merely better")
    assert _blame_with(link=2.0, best=9.0, ours=4.6), (
        "machine NOT listed on 2.0 Mbit/s against a witness of 9.0 -- the "
        "ratio has stopped deciding anything")


def _loop(links, ours=4.6):
    """Replay `_rent`'s blame path over a sequence of probe readings. `best_link`
    is raised before the machine is judged, exactly as `_rent` does it, so what
    comes out is what the real loop would do."""
    best, banned = 0.0, []
    for i, link in enumerate(links):
        best = max(best, link)
        if _blame_with(link=link, best=best, ours=ours):
            banned.append(i)
    return banned


def test_the_permanent_list_is_reachable_at_the_default_floor():
    """A guard that can never fire is not a guard: a machine reaches
    `blame_machine` only after being rejected, so every reading in `best_link` is
    below the rejection floor, and the two floors must not meet."""
    from booksmith.core import knobs
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
    """The whole rent loop, not one call: a sick path bans no machine. A probe
    that receives one byte in twelve seconds returns 6.7e-07 and not zero, so the
    witness has a floor of its own; three shapes of a sick path are driven here."""
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
    """`best_link` is a maximum and never decays, so a witness goes stale: a
    reading taken while our own path was six times faster is no contrast. The
    guard re-measures our downlink at the moment of blaming."""
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
    """The commonest zero: `best_link < 3 * link` reads `0.0 < 0.0` -- False -- so
    the machine went onto the permanent list with nothing to compare it against.
    Both directions, because only one of them goes wrong."""
    assert _blame_with(link=0.0, best=0.0, ours=4.6) == [], (
        "machine listed FOREVER on a zero probe while NO machine had yet "
        "given us anything over ssh -- there is no witness at all, and this "
        "is how a dead path at our end bans the whole market")
    assert _blame_with(link=0.0, best=5.0, ours=4.6), (
        "machine NOT listed on a zero probe although another gave 5.0 over "
        "the same ssh -- that witness is exactly what the list is for")


def test_a_failed_blacklist_write_does_not_kill_the_rental():
    """Failing to write down a ban may not abandon a running machine: `mark_bad`
    writes a file, and a read-only ledger directory would take the whole rental
    out of the middle of `_rent`, machine taken and billing."""
    said = []

    def refuses(mid, why):
        raise PermissionError("[Errno 13] the ledger directory is read-only")

    got = runner.blame_machine({"machine_id": 5}, "trial", ours=4.6, link=0.1,
                               best_link=9.0, mark=refuses, say=said.append)
    assert got is False, "a failed write was reported as a successful ban"
    assert any("could NOT be written" in line for line in said), (
        f"the failure to record the ban was swallowed: {said}")


def test_a_floor_that_is_not_a_number_is_refused_before_any_money():
    """`nan` compares False with everything: `MIN_LINK_MBPS=nan` makes `link >=
    floor` and `link < floor` both false, so every machine falls through to "the
    reason was not named". A typo that costs money refuses before the rental."""
    import os
    was = os.environ.get("MIN_LINK_MBPS")
    for bad in ("nan", "inf", "-1", "narrow"):
        os.environ["MIN_LINK_MBPS"] = bad
        try:
            runner._min_link_mbps()
        except Refusal as e:
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
    """`BOOKSMITH_LEDGER` may be a bare name, and both writers must cope:
    `os.path.dirname("bad-machines.json")` is `""` and `os.makedirs("")` raises.
    Both are called here, not read: a grep would pass on a third copy."""
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
    """`ours` sets the floor and gates the blacklist, so it must be recorded: a
    number that decides a permanent ban and lives only in a comment is the "log
    the quantity" rule broken at the source. Driven, not declared: `_rent` runs."""
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
    except BaseException:
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
    """The rejection floor takes no part in the permanent-list verdict: one knob
    doing two opposite jobs turned a ban into a pass when the floor was lowered.
    It is gone from the signature, which is the firmest form of the ban."""
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
    """The pauses grow, and their sum stays under the dead man's grace: a refusal
    by rate answered at the same rate cost the key its access, and waiting past
    that grace is paying to wait for a machine that puts itself out."""
    from booksmith.remote.vast import Vast
    steps = list(Vast.RETRY_S)
    assert steps == sorted(steps) and steps[-1] > steps[0] * 4, (
        f"the backoffs do not grow: {steps}. A refusal by rate must not be "
        f"answered at the same rate")
    assert sum(steps) < 900, (
        f"the backoffs sum to {sum(steps)} s, not under the dead man's "
        f"grace (900 s) -- we wait longer than the machine lives alone")


def test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine():
    """403 and 429 are a refusal of access, not "the machine disobeyed": a retry
    cures the second and worsens the first, and the `alive` check that follows
    answers "alive" only because there is nobody to ask."""
    import time as _t

    from booksmith.remote import vast as vmod

    was_sleep = _t.sleep
    v = vmod.Vast.__new__(vmod.Vast)
    v.v = _FakeVastApi("403 Client Error: Forbidden")
    _t.sleep = lambda s: None
    try:
        with support.said() as stated:
            assert v.destroy(1) is False
    finally:
        _t.sleep = was_sleep
    everything = "\n".join(stated)
    assert "REFUSAL OF ACCESS" in everything, (
        f"403 named as an ordinary destroy failure:\n{everything[:400]}")
    assert "nobody to ask" in everything, (
        '"alive" after a refusal of access is passed off as an observation')


class _BoxThatFailsAfterPulse:
    """A machine whose pulse started and whose link then broke: the pulse starts
    before the first network command, and that command can fail normally."""

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
    """A failure after `start_heartbeat` must put the pulse out: our thread
    touching `/root/.alive` every 30 s switches off the dead man's watch, the one
    way of putting a machine out that needs neither our key nor our process."""
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
