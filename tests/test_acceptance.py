"""Reports are compared whole, because the headline numbers are blind.

The five figures everyone quotes -- 698/1232 found, 646 whole, 375 merged, 501
extra jumps, 89.4 % ink -- survived a full rename of all 13 996 Cyrillic keys
in `bench/annopage` without moving. They also survived the rename being stopped
halfway. What moved was the prose around them: a line reading "on an object
outside scoring: 350" stopped being printed, and 350 excluded boxes were charged
to the model instead.

So these checks compare every line. `booksmith.acceptance` holds the command
table and the snapshots live in `tests/expected/`.

WHAT THESE CHECKS DO NOT SEE. Each report is produced by a SUBPROCESS, so an
in-memory mutation of `metrics` or `policy` never reaches them. That is the
right shape for their job -- they are run against the tree after each step of
the translation, and they compare what the tree actually prints. Proved by
damaging the tree instead of memory: dropping one lookup of the
outside-scoring bucket in `metrics.py` turned "spurious_box: 110" into 460 and
deleted the line "on an object outside scoring: 350", and the diff named both.

A missing bench is a SKIP WITH A REASON, never a pass. Most of what these
commands read is behind .gitignore -- `bench/*/detect/pages` and the six
synthetic books -- so on a fresh clone most of them cannot run. The runner
counts skips as their own number for exactly this case.

THE RECORDS. Beside each report the raw result dict is kept as JSON
(`acceptance.RECORDS`), computed in process and compared key by key at 1e-6.
A report can stay identical while a key nobody prints moves; the record sees
it. And a record taken against other truth is reported as INPUTS MOVED, not
as a change: the two must not read alike.

A REBUILT BENCH IS RED, NOT A SKIP, on purpose. `bench/slovar` is untracked
and rebuilt locally; its truth is byte-identical on rebuild (measured) but
its manifest carries the commit marker of the build. The record names the
input that moved and says whether the numbers moved with it; the person
re-saves it having read that line.
"""
import os

import pytest

import support
from booksmith.datasets import accept as acceptance


def _one(name):
    gone = acceptance.missing(name)
    if gone:
        pytest.skip(f"no input: {', '.join(gone)}")
    if not os.path.isfile(acceptance.path(name)):
        pytest.skip(f"no snapshot {acceptance.path(name)}: "
                     "take one with `python3 tools/acceptance.py --save`")
    d = acceptance.differs(name)
    assert not d, (f"report {name} diverged from its snapshot:\n"
                   + "\n".join(d[:40]))


def test_score_on_annopage_reports_the_same_report():
    """600 real pages: the widest report the project has."""
    _one("score-annopage")


def test_score_on_hard_reports_the_same_report():
    """The only tracked bench that mixes annotated text with unannotated.

    `bench/annopage` annotates no text at all, so its text half reads NOT
    MARKED whatever happens to it. `bench/hard` is 124 AnnoPage pages plus 6
    synthetic ones, and it is the only place where the caption "counted over 6
    pages of 130" exists to be lost.
    """
    _one("score-hard")


def test_text_on_slovar_reports_the_same_report():
    """Truth against itself: the one input where reading has a known answer."""
    _one("text-slovar")


def test_replay_check_reports_the_same_report():
    """`replay --check` returns 1 whether or not anything is wrong.

    Measured: 38 of 55 values present in the snapshot, rc=1, both before and
    after damage. The return code carries no signal here -- only the report
    does, which is why it is compared as text.
    """
    _one("replay-annopage")


def test_help_reports_the_same_text():
    """Nothing else in the suite reads the help at all.

    `grep` over `tests/` finds no occurrence of `help=`, `description=` or
    `--help`: 86 help strings and a 36-line module docstring could go wrong,
    empty or misleading and every check would stay green.
    """
    _one("help")


def test_the_command_table_covers_every_format_the_migration_touches():
    """A snapshot set that misses a format is a blind spot wearing a number."""
    argv = " ".join(a for c, _ in acceptance.COMMANDS.values() for a in c)
    # NOT `detect/pages`: a run lives under its model's name now
    # (`detect/<label>/pages`), and pinning one model here would make the
    # table's coverage depend on which detector happens to be measured.
    for needed in ("truth", "/detect/", "/pages", "--help"):
        assert needed in argv, f"no acceptance command reads {needed}"
    assert len(acceptance.COMMANDS) >= 5


def test_the_reading_probe_battery_reports_the_same():
    """A report can be identical while the PROBE behind it has stopped working.

    Measured during the key migration: renaming the normalisation level
    to `none` in `NORM_STEPS` and not at the place that compares against it
    made `--norm none` do exactly what `boundary` does -- three levels became
    two -- and the probe that guarded that distinction threw `TextError`
    instead of measuring. `text-slovar` was byte-identical throughout. Only
    this line moved: "UNCAUGHT 0" became 1.
    """
    _one("text-selfcheck")


def _record(name):
    gone = acceptance.record_missing(name)
    if gone:
        pytest.skip(f"no input: {', '.join(gone)}")
    if not os.path.isfile(acceptance.record_path(name)):
        pytest.skip(f"no record {acceptance.record_path(name)}: "
                     "take one with `python3 tools/acceptance.py --save`")
    d = acceptance.record_differs(name)
    assert not d, (f"record {name} diverged from its snapshot:\n"
                   + "\n".join(d[:40]))


def test_the_contour_probe_battery_reports_the_same():
    """33 probe names were quoted in prose and verified by nothing."""
    _one("score-selfcheck")


def test_the_fitness_probe_battery_reports_the_same():
    """21 probe names, one of them uncaught on slovar by construction.

    The command returns 1 there (the dark column probe); the lock is the text,
    and a probe that silently changed its name or its verdict moves the text.
    """
    _one("fitness-selfcheck")


def test_the_contour_record_on_annopage_is_the_same_dict():
    _record("score-annopage")


def test_the_contour_record_on_hard_is_the_same_dict():
    _record("score-hard")


def test_the_reading_record_on_slovar_is_the_same_dict():
    _record("text-slovar")


def test_the_fitness_record_on_slovar_is_the_same_dict():
    _record("fitness-slovar")


def test_a_record_against_other_inputs_says_inputs_moved_not_changed():
    """A rebuilt bench must not pass as the same bench with a moved number."""
    import json
    import tempfile
    name = "text-slovar"
    if acceptance.record_missing(name) or not os.path.isfile(
            acceptance.record_path(name)):
        pytest.skip("no text-slovar record to test against")
    with open(acceptance.record_path(name), encoding="utf-8") as f:
        want = json.load(f)
    want["inputs"] = {k: "0" * 64 for k in want["inputs"]}
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, name + ".json")
        with open(fake, "w", encoding="utf-8") as f:
            json.dump(want, f)
        real = acceptance.record_path
        try:
            acceptance.record_path = lambda n: fake
            d = acceptance.record_differs(name)
        finally:
            acceptance.record_path = real
    assert d and d[0].startswith("INPUTS MOVED"), d
    assert "bench/slovar/truth" in d[0], d[0]
    assert d[1].startswith("  (the result is the same"), d[1]


def test_the_record_diff_sees_a_moved_number_and_a_lost_key():
    a = {"x": {"n": 1.0, "s": "a", "l": [1, 2]}, "gone": 0}
    b = {"x": {"n": 1.0000001, "s": "b", "l": [1, 2, 3]}, "new": 0}
    out = acceptance._walk_diff(a, b, "", [])
    assert "/x/n" not in " ".join(out), "1e-7 is inside the tolerance"
    moved = acceptance._walk_diff({"n": 1.0}, {"n": 1.001}, "", [])
    assert moved == ["/n: 1.0 -> 1.001"], f"1e-3 must be caught: {moved}"
    assert any(p.startswith("/x/s") for p in out)
    assert any(p.startswith("/x/l") for p in out)
    assert "/gone: key gone" in out and "/new: new key" in out
    nan = float("nan")
    assert acceptance._walk_diff({"n": 0.5}, {"n": nan}, "", []) == ["/n: 0.5 -> nan"]
    assert acceptance._walk_diff({"n": nan}, {"n": nan}, "", []) == []


def test_the_built_book_reports_the_same_swaps():
    """`books html` and `books apply` were read by no report at all.

    Three of the seven defects the key migration left lived there and nowhere
    else: three sheet counters frozen at zero while the book itself marked two
    sheets, a CSS selector left in Russian so 500 furniture blocks stopped
    being dimmed, and a file quietly dropped out of `assets/source`.
    """
    _one("apply-status")


def test_the_slovar_truth_lock_still_matches_the_bench_on_disk():
    """The step-0 lock: 13 truth files by sha256, and NOTHING READ IT.

    It was written to prove that moving the generator changed no truth, and
    it did prove it -- by hand, `sha256sum -c`, twice. A lock checked by hand
    is checked until someone forgets, and then it is a file that agrees with
    nothing. It is read here now, so that a generator change that moves the
    truth says so in the suite rather than in a number three steps later.

    `bench/slovar` is untracked and rebuilt locally, so a missing truth is a
    skip with a reason. A truth that is THERE and differs is a failure: the
    truth is the answer every reading number on this book is measured
    against.
    """
    import hashlib
    root_ = os.path.dirname(os.path.dirname(support.SRC))
    lock = os.path.join(root_, "tests", "expected", "slovar-truth.sha256")
    root = os.path.join(root_, "bench", "slovar")
    if not os.path.isdir(os.path.join(root, "truth")):
        pytest.skip("no bench/slovar/truth: build it with "
                     "`books synth --book slovar --out bench/slovar`")
    want = [l.split("  ", 1) for l in
            open(lock, encoding="utf-8").read().splitlines() if l.strip()]
    assert want, f"{lock} is empty -- a lock over nothing"
    bad = []
    for digest, rel in want:
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            bad.append(f"{rel}: gone")
            continue
        got = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if got != digest:
            bad.append(f"{rel}: {got[:12]} against {digest[:12]}")
    assert not bad, (
        f"the slovar truth moved from its lock ({len(bad)} of {len(want)} "
        f"files): {bad[:5]}. If the generator was MEANT to change, re-take "
        f"the lock: cd bench/slovar && sha256sum truth/*.json > "
        f"../expected/slovar-truth.sha256")


def test_a_skip_is_not_a_pass():
    """The exit code has to say that nothing was proved.

    It did not. The skip branch printed and left `rc` alone, so a run that
    proved nothing returned 0 -- and this is the per-commit invariant, read by
    its exit code. Measured on a tree with one run moved a directory deeper:
    the reports that read it skipped and the tool still said 0. Every path
    these reports read is behind .gitignore, so the day a rename empties a
    glob looks exactly like the day someone clones the repository. The first
    of those must be red; `--allow-skips` is for the second.
    """
    import io
    import contextlib
    real = acceptance.missing
    try:
        acceptance.missing = lambda name: (
            ["bench/nowhere/detect/pages"] if name == "help" else real(name))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = acceptance.main([])
        assert rc == 1, "a skipped report passed"
        assert "proved NOTHING" in out.getvalue(), out.getvalue()[-300:]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = acceptance.main(["--allow-skips"])
        assert rc == 0, "--allow-skips did not accept proving less"
        assert "proved NOTHING" in out.getvalue(), (
            "--allow-skips went quiet about it")
    finally:
        acceptance.missing = real
