import inspect
import time
import pytest
from fleet.errors import Refusal

pytest.importorskip("vastai")
from fleet import box as rbox
from fleet import ledger
from fleet import runner
import support


class _FakeSsh(rbox.Box):
    def __init__(self):
        self.seen = None

    _ssh = ["ssh"]
    _addr = "root@nowhere"


class _Stream:
    def __init__(self, mbps, total=None, clock=None):
        self.mbps = mbps
        self.clock = clock if clock is not None else [0.0]
        self.total, self.sent = (total, 0)
        self.stdout = self

    QUANTUM = 0.01

    def read(self, n):
        if self.total is not None and self.sent >= self.total:
            return b""
        give = int(self.mbps * 1000000.0 / 8 * self.QUANTUM)
        give = min(n, give) if self.total is None else min(n, give, self.total - self.sent)
        self.clock[0] += self.QUANTUM
        self.sent += give
        return b"\x00" * give

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _probe_at(mbps, seconds=0.6, total=None):
    return _probe_timed(mbps, seconds, total)[0]


class _Clock:
    def __init__(self, at):
        self.at = at

    def time(self):
        return self.at[0]


def _probe_timed(mbps, seconds=0.6, total=None):
    import subprocess

    clock = [1000.0]
    stream = _Stream(mbps, total, clock)
    ran = []
    was_popen, was_time = (subprocess.Popen, rbox.time)

    def spy(cmd, *a, **k):
        ran.append(cmd)
        return stream

    subprocess.Popen = spy
    rbox.time = _Clock(clock)
    try:
        got = _FakeSsh().probe(seconds=seconds)
        return (got, clock[0] - 1000.0, ran[0] if ran else None)
    finally:
        subprocess.Popen = was_popen
        rbox.time = was_time


def test_a_narrow_channel_is_measured_not_called_broken():
    narrow = _probe_at(1.16)
    assert 1.1 <= narrow <= 1.25, (
        f"a 1.16 Mbit/s channel measured as {narrow:.2f} -- under a clock this probe controls, the arithmetic is exact, and anything else is the arithmetic being wrong"
    )
    assert narrow > 0.5, (
        f'a 1.16 Mbit/s channel measured as {narrow:.2f} -- the probe again confuses "we are slow" with "the machine is broken"'
    )
    assert narrow < 3.0, f"measured {narrow:.2f} instead of ~1.16 -- the probe lies upward"


def test_a_broken_machine_still_gives_a_number_below_any_floor():
    broken = _probe_at(0.062)
    assert 0.055 <= broken <= 0.07, (
        f"a 62 kbit/s machine measured as {broken:.4f} -- exact arithmetic over an exact clock must give back what was put in"
    )
    assert broken < 0.3, (
        f"a 62 kbit/s machine measured as {broken:.2f} Mbit/s -- the probe no longer tells a broken one from a slow one"
    )
    healthy = _probe_at(50.0)
    assert 47.0 <= healthy <= 53.0, (
        f"a 50 Mbit/s machine measured as {healthy:.1f} -- exact in, exact out, or the arithmetic is wrong"
    )
    assert healthy > 10.0, f"a healthy machine measured as {healthy:.1f} Mbit/s -- the probe reads low"


def test_the_probe_stops_ON_TIME_and_not_on_a_byte_count():
    slack = _Stream.QUANTUM
    for mbps in (0.062, 1.16, 50.0):
        _, took, _cmd = _probe_timed(mbps, seconds=0.6)
        assert took <= 0.6 + 2 * slack, (
            f"at {mbps} Mbit/s the probe ran {took:.3f} s of the 0.6 it was given -- it is waiting for a SIZE, and a slow machine will be written down as a broken one, which is the defect this probe was written to end"
        )
        assert took >= 0.6 - slack, (
            f"at {mbps} Mbit/s the probe gave up after {took:.3f} s of 0.6 -- it stopped on a byte count, and one early chunk is the TCP ramp-up, not the channel"
        )


def test_the_probe_asks_THE_MACHINE_and_asks_it_for_a_bounded_stream():
    _, _, cmd = _probe_timed(50.0, seconds=0.6)
    assert cmd is not None, "the probe started no process at all"
    argv = cmd if isinstance(cmd, list) else [cmd]
    joined = " ".join(str(x) for x in argv)
    assert argv[0] == "ssh" and _FakeSsh._addr in argv, (
        f"the probe did not go to the machine over ssh: {argv}. It measured something, and the something was not the link"
    )
    assert "/dev/urandom" in joined, (
        f"the probe asks for something other than random bytes: {joined}. Zeros compress in ssh and give a pretty lie"
    )
    assert "head -c" in joined, (
        f"the probe asks for an UNBOUNDED stream: {joined}. `mb_cap` is the only thing stopping a machine that is billing from sending forever"
    )


def test_the_probe_divides_by_the_time_it_actually_took():
    mbps, seconds = (30.0, 0.6)
    bytes_in_a_third = int(mbps * 1000000.0 / 8 * (seconds / 3))
    got, took, _ = _probe_timed(mbps, seconds=seconds, total=bytes_in_a_third)
    assert took < 0.9 * seconds, (
        f"the stream ended after a third and the probe still ran {took:.2f} of {seconds} s -- it is not noticing the end of the stream"
    )
    assert 0.7 * mbps <= got <= 1.4 * mbps, (
        f"a stream that ended early measured {got:.1f} against {mbps} -- the probe divides by the budget it was given, not by the time it used, so every early end reads as a slow machine"
    )


def test_a_dead_channel_is_the_only_zero():
    assert _probe_at(0.0, total=0) == 0.0, "a dead pipe gave a non-zero"


class _FakeVast:
    def __init__(self):
        self.boot_timeout = None

    def wait_running(self, iid, timeout):
        self.boot_timeout = timeout
        raise RuntimeError("no further: the deadline is caught")

    def attach_key(self, *a):
        pass


def _blame_with(link, best, ours, limit=None):
    recorded = []
    runner.blame_machine(
        {"machine_id": 777},
        "trial",
        ours=ours,
        link=link,
        best_link=best,
        mark=lambda mid, why: recorded.append((mid, why)),
        say=lambda *a: None,
    )
    return recorded


def test_a_machine_is_blamed_only_with_a_witness():
    assert _blame_with(link=0.25, best=0.34, ours=4.6) == [], (
        "machine listed FOREVER although the best one seen gave only 0.34 against its 0.25 -- no witness that the machine is at fault"
    )
    assert _blame_with(link=0.25, best=7.0, ours=4.6), (
        "machine NOT listed although another over the same ssh gave 7.0 against its 0.25 -- this is exactly the machine's fault"
    )
    assert _blame_with(link=0.25, best=7.0, ours=0.0) == [], "listed while our own channel was not measured"
    assert _blame_with(link=2.0, best=3.0, ours=4.6) == [], (
        "machine listed FOREVER on 2.0 Mbit/s while the best seen was 3.0 -- a witness must be three times better, not merely better"
    )
    assert _blame_with(link=2.0, best=9.0, ours=4.6), (
        "machine NOT listed on 2.0 Mbit/s against a witness of 9.0 -- the ratio has stopped deciding anything"
    )


def _loop(links, ours=4.6):
    best, banned = (0.0, [])
    for i, link in enumerate(links):
        best = max(best, link)
        if _blame_with(link=link, best=best, ours=ours):
            banned.append(i)
    return banned


def test_the_permanent_list_is_reachable_at_the_default_floor():
    from fleet import knobs

    floor = float(knobs.KNOB["MIN_LINK_MBPS"].default)
    assert runner.WITNESS_MBPS < floor, (
        f"the witness floor {runner.WITNESS_MBPS} has reached the rejection floor {floor}. Every witness is a REJECTED machine, so its reading is below the rejection floor by construction -- the permanent list can then never fire at all"
    )
    assert _loop([1.5, 0.1]) == [1], (
        f"a machine reading 0.1 Mbit/s beside one that managed 1.5 was NOT blacklisted: at the default floor of {floor} both are rejected, so this is the only shape a witness can take, and the list is empty without it"
    )


def test_a_path_dying_at_our_end_blames_nobody_at_all():
    for name, links in (
        ("one 64 KiB chunk", [0.0437, 0.0, 0.0, 0.0, 0.0]),
        ("one byte in twelve seconds", [6.67e-07, 0.0, 0.0, 0.0, 0.0]),
        ("every machine dribbles", [0.05, 0.008, 0.012, 0.006, 0.009]),
        ("only 62 kbit/s machines", [0.0, 0.0, 0.062, 0.0, 0.062]),
    ):
        banned = _loop(links)
        best = max(links)
        assert not banned, (
            f"{name}: machines {banned} went onto the PERMANENT list while the best anyone gave us was {best:.4g} Mbit/s -- that is our path, not theirs, and the list has no undo"
        )
    best = max(0.0, 7.0)
    assert _blame_with(link=0.25, best=best, ours=4.6), (
        "with a witness at 7.0 Mbit/s a machine giving 0.25 was NOT listed -- the floor has swallowed the rule it was added to"
    )


def test_a_path_that_sagged_mid_loop_condemns_nobody():
    recorded = []
    got = runner.blame_machine(
        {"machine_id": 9},
        "trial",
        ours=20.0,
        ours_now=3.0,
        link=2.2,
        best_link=7.0,
        mark=lambda mid, why: recorded.append(mid),
        say=lambda *a: None,
    )
    assert got is False and (not recorded), (
        "a machine was listed FOREVER on a contrast with a witness measured while our own path was six times faster than it is now"
    )
    assert runner.blame_machine(
        {"machine_id": 9},
        "trial",
        ours=20.0,
        ours_now=19.0,
        link=2.2,
        best_link=7.0,
        mark=lambda *a: None,
        say=lambda *a: None,
    ), (
        "our path was steady and the machine still escaped: the sag guard has swallowed the rule it was added beside"
    )


def test_a_zero_probe_with_no_witness_at_all_blames_nobody():
    assert _blame_with(link=0.0, best=0.0, ours=4.6) == [], (
        "machine listed FOREVER on a zero probe while NO machine had yet given us anything over ssh -- there is no witness at all, and this is how a dead path at our end bans the whole market"
    )
    assert _blame_with(link=0.0, best=5.0, ours=4.6), (
        "machine NOT listed on a zero probe although another gave 5.0 over the same ssh -- that witness is exactly what the list is for"
    )


def test_a_failed_blacklist_write_does_not_kill_the_rental():
    said = []

    def refuses(mid, why):
        raise PermissionError("[Errno 13] the ledger directory is read-only")

    got = runner.blame_machine(
        {"machine_id": 5}, "trial", ours=4.6, link=0.1, best_link=9.0, mark=refuses, say=said.append
    )
    assert got is False, "a failed write was reported as a successful ban"
    assert any("could NOT be written" in line for line in said), (
        f"the failure to record the ban was swallowed: {said}"
    )


def test_a_floor_that_is_not_a_number_is_refused_before_any_money():
    import os

    was = os.environ.get("MIN_LINK_MBPS")
    for bad in ("nan", "inf", "-1", "narrow"):
        os.environ["MIN_LINK_MBPS"] = bad
        try:
            runner._min_link_mbps()
        except Refusal as e:
            assert "MIN_LINK_MBPS" in str(e), e
        else:
            raise AssertionError(f"MIN_LINK_MBPS={bad!r} was accepted as a rejection floor")
        finally:
            if was is None:
                os.environ.pop("MIN_LINK_MBPS", None)
            else:
                os.environ["MIN_LINK_MBPS"] = was
    assert runner._min_link_mbps() >= 0, "the real floor stopped working"


def test_both_journal_writers_survive_a_bare_file_name():
    import os
    import tempfile

    tmp = tempfile.mkdtemp()
    was = os.getcwd()
    os.chdir(tmp)
    try:
        ledger.mark_bad(4242, "trial", path="bad-machines.json")
        assert os.path.isfile(os.path.join(tmp, "bad-machines.json")), (
            "mark_bad wrote nothing where a bare file name was given"
        )
        ledger.append(ledger.Run(job="trial", image="none", gpu="none"), path="ledger.jsonl")
        assert os.path.isfile(os.path.join(tmp, "ledger.jsonl")), (
            "append wrote nothing where a bare file name was given"
        )
    finally:
        os.chdir(was)


def test_the_channel_that_decides_reaches_the_ledger():
    from dataclasses import asdict

    row = asdict(ledger.Run(job="t", image="i", gpu="g"))
    assert "our_downlink_mbps" in row, f"the ledger row does not carry our own downlink: {sorted(row)}"
    assert row["our_downlink_mbps"] is None, (
        "the default is not None -- NOT MEASURED would be written as 0.0, and 0.0 is what makes `blame_machine` refuse to act"
    )
    rec = ledger.Run(job="t", image="i", gpu="g")
    was = runner._our_downlink_mbps
    runner._our_downlink_mbps = lambda *a, **k: 3.25
    try:
        runner._rent(_RefusingVast(), _spec(), None, {}, rec, [], time.time())
    except BaseException:
        pass
    finally:
        runner._our_downlink_mbps = was
    assert rec.our_downlink_mbps == 3.25, (
        f"`_rent` measured our downlink and did not write it down: {rec.our_downlink_mbps!r}. It decides the rejection floor and gates a permanent ban, and the ledger would say nothing about it"
    )


class _RefusingVast:
    def offers(self, *a, **k):
        return []

    def show_instances(self):
        return []


def _spec():
    from fleet.spec import JobSpec

    return JobSpec(name="trial", image="none", command="true")


def test_the_verdict_cannot_depend_on_the_rejection_floor():
    names = set(inspect.signature(runner.blame_machine).parameters)
    assert "limit" not in names and "floor" not in names, (
        f"the floor is back in the permanent-list guard: {sorted(names)}. Loosening it to let machines through would make banning easier"
    )


class _FakeVastApi:
    def __init__(self, err):
        self.err, self.calls = (err, 0)

    def destroy_instance(self, id):
        self.calls += 1
        raise RuntimeError(self.err)

    def show_instances(self):
        self.calls += 1
        raise RuntimeError(self.err)


def test_destroy_backs_off_instead_of_hammering():
    from fleet.vast import Vast

    steps = list(Vast.RETRY_S)
    assert steps == sorted(steps) and steps[-1] > steps[0] * 4, (
        f"the backoffs do not grow: {steps}. A refusal by rate must not be answered at the same rate"
    )
    assert sum(steps) < 900, (
        f"the backoffs sum to {sum(steps)} s, not under the dead man's grace (900 s) -- we wait longer than the machine lives alone"
    )


def test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine():
    import time as _t
    from fleet import vast as vmod

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
    assert "REFUSAL OF ACCESS" in everything, f"403 named as an ordinary destroy failure:\n{everything[:400]}"
    assert "nobody to ask" in everything, '"alive" after a refusal of access is passed off as an observation'


class _BoxThatFailsAfterPulse:
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
    _BoxThatFailsAfterPulse.declared = []
    was = runner.Box
    runner.Box = _BoxThatFailsAfterPulse
    try:
        for iid in (1001, 1002):
            try:
                runner.connect(_FakeVastReady(), iid, _SpecStub(), None, attempt_limit=60.0)
            except OSError:
                pass
    finally:
        runner.Box = was
    declared_n = _BoxThatFailsAfterPulse.declared
    assert len(declared_n) == 2, (
        f"the stub machine was made {len(declared_n)} times instead of two -- the check never reached the place it guards"
    )
    live = [i for i, b in enumerate(declared_n, 1) if b.pulse]
    assert not live, (
        f"after the link failed the pulse stayed alive on machines {live}. Our thread would revive an abandoned machine all run, its dead-man's watch off -- whoever started it must stop it"
    )


class _FakeVastReady:
    def wait_running(self, iid, timeout):
        pass

    def ssh_target(self, iid):
        return ("root", "10.0.0.1", 22)

    def attach_key(self, *a):
        pass


class _SpecStub:
    workdir = "/workdir"
