"""The locks: a metric's raw result dict, and a command's report, verbatim.

WHY WHOLE REPORTS AND NOT FIVE NUMBERS. The five headline figures were tried
against a real migration and they are blind: renaming all 13 996 Cyrillic keys
of `bench/annopage` and leaving the code alone moved not one of them, nor did
stopping the rename halfway. What moved was the prose around them -- a line
reading "on an object outside scoring: 350" stopped being printed, and 350
excluded boxes were charged to the model instead; "sha256 checked" became "no
such field", collapsing the difference between checked and unable to check.

WHY THE RECORDS BESIDE THE REPORTS. A report is prose, and prose can be
rearranged without a number moving. The reverse also happens: a result dict
grows a key no report prints, or one the report rounds. So the RAW DICT is kept
as JSON, floats rounded to six places, compared key by key at 1e-6 -- and that
is the lock a package move is measured with: a metric moved to another file
must return the same dict to the last key.

A missing input is a skip with a reason, never a pass: most of what these read
is behind .gitignore, so a fresh clone can prove little. `slovar` is drawn by
the fixture, so the reading record is measured everywhere.

To re-take a lock, run the command and write its output to the file the test
names; there is no blanket save, on purpose -- a blanket save blesses every
other lock blind.
"""
import difflib
import json
import os
import re
import subprocess
import sys

import pytest

from booksmith.core.config import ROOT

EXPECTED = os.path.join(ROOT, "tests", "expected")
TOLERANCE = 1e-6

# The clock on every log line moves on its own. So does the hash of a SOURCE
# file as it is now -- `replay --check` prints it to say the snapshot was taken
# with other code, and it changes on every edit to the adapter, comments
# included. The hash IN THE SNAPSHOT is data and is kept.
_CLOCK = re.compile(r"^\[\d\d:\d\d:\d\d\] ", re.M)
_TREE_HASH = re.compile(r"(tree )[0-9a-f]{8,}")


def _lock(name):
    return os.path.join(EXPECTED, name + ".txt")


def _need(paths):
    gone = [p for p in paths if not os.path.exists(os.path.join(ROOT, p))]
    if gone:
        pytest.skip(f"no input: {', '.join(gone)}")


def _run(argv):
    """The command's output, verbatim but for the clock, stdout and stderr.

    COLUMNS is pinned because argparse wraps to the terminal width: at
    COLUMNS=40 one report differed by 76 lines while nothing had changed. A
    snapshot that depends on the window it was taken in is not a snapshot.
    """
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), COLUMNS="80")
    r = subprocess.run([sys.executable, "-m", "booksmith.cli"] + argv,
                       cwd=ROOT, capture_output=True, text=True, env=env)
    out = _CLOCK.sub("", r.stdout + r.stderr)
    return _TREE_HASH.sub(r"\1<current source>", out)


def _report(name, argv, needs):
    _need(needs)
    assert os.path.isfile(_lock(name)), f"no lock {_lock(name)}"
    want = open(_lock(name), encoding="utf-8").read().splitlines()
    got = _run(argv).splitlines()
    d = [ln for ln in difflib.unified_diff(want, got, "expected", "now",
                                           lineterm="", n=1)]
    assert not d, (f"the report diverged from {_lock(name)}:\n"
                   + "\n".join(d[:40]))


def _clean(o):
    """JSON-ready: floats rounded, tuples listed, sets sorted, numpy unboxed."""
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return sorted(_clean(v) for v in o)
    if hasattr(o, "item"):
        return _clean(o.item())
    return o


def _walk_diff(want, got, at, out):
    """Every path where two cleaned dicts differ beyond TOLERANCE."""
    if isinstance(want, dict) and isinstance(got, dict):
        for k in sorted(set(want) | set(got)):
            if k not in want:
                out.append(f"{at}/{k}: new key")
            elif k not in got:
                out.append(f"{at}/{k}: key gone")
            else:
                _walk_diff(want[k], got[k], f"{at}/{k}", out)
    elif isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            out.append(f"{at}: {len(want)} items -> {len(got)}")
        for i, (a, b) in enumerate(zip(want, got)):
            _walk_diff(a, b, f"{at}[{i}]", out)
    elif (isinstance(want, (int, float)) and isinstance(got, (int, float))
          and not isinstance(want, bool) and not isinstance(got, bool)):
        # NaN FIRST: `abs(x - nan) > t` is False for every x, so a metric that
        # started returning NaN where it returned 0.5 read as "same record".
        if (want != want) != (got != got):
            out.append(f"{at}: {want} -> {got}")
        elif want == want and abs(want - got) > TOLERANCE:
            out.append(f"{at}: {want} -> {got}")
    elif want != got:
        out.append(f"{at}: {want!r} -> {got!r}")
    return out


def _record(name, result):
    path = os.path.join(EXPECTED, name + ".json")
    assert os.path.isfile(path), f"no record {path}"
    with open(path, encoding="utf-8") as f:
        want = json.load(f)["result"]
    d = _walk_diff(want, _clean(result), "", [])
    assert not d, (f"the record diverged from {path} at {len(d)} paths:\n"
                   + "\n".join(d[:40]))


# ------------------------------------------------------------- the records

def test_the_contour_record_on_annopage_is_the_same_dict():
    """600 real pages: the widest measurement the project has."""
    from booksmith.datasets.metrics import contour
    args = ["bench/annopage/truth", "bench/annopage/detect/PP-DocLayoutV2/pages"]
    _need(args)
    _record("score-annopage", contour.compare(*[os.path.join(ROOT, a) for a in args]))


def test_the_contour_record_on_hard_is_the_same_dict():
    """The only tracked bench that mixes annotated text with unannotated: 124
    AnnoPage pages and 6 drawn ones, where the coverage caption exists to be
    lost."""
    from booksmith.datasets.metrics import contour
    args = ["bench/hard/truth", "bench/hard/detect/PP-DocLayoutV2/pages"]
    _need(args)
    _record("score-hard", contour.compare(*[os.path.join(ROOT, a) for a in args]))


def test_the_reading_record_on_slovar_is_the_same_dict(slovar):
    """Truth against itself: the one input where reading has a known answer.

    The bench is drawn by the fixture rather than read from the tree, so this
    record is measured on every machine -- and it is the lock that says the
    drawn truth and the reading metric still agree to the last key.
    """
    from booksmith.datasets.metrics import text
    _record("text-slovar", text.measure(slovar.truth_dir, slovar.truth_dir))


def test_the_fitness_record_on_slovar_is_the_same_dict():
    from booksmith.processing.assess import ink
    args = ["bench/slovar/slovar.pdf",
            "bench/slovar/detect/PP-DocLayoutV2/pages", "bench/slovar/truth"]
    _need(args)
    _record("fitness-slovar", ink.measure(*[os.path.join(ROOT, a) for a in args]))


def test_the_record_diff_sees_a_moved_number_and_a_lost_key():
    """The comparer itself, on made-up dicts: a lock compared by a blind
    comparer is a file that agrees with everything."""
    a = {"x": {"n": 1.0, "s": "a", "l": [1, 2]}, "gone": 0}
    b = {"x": {"n": 1.0000001, "s": "b", "l": [1, 2, 3]}, "new": 0}
    out = _walk_diff(a, b, "", [])
    assert "/x/n" not in " ".join(out), "1e-7 is inside the tolerance"
    moved = _walk_diff({"n": 1.0}, {"n": 1.001}, "", [])
    assert moved == ["/n: 1.0 -> 1.001"], f"1e-3 must be caught: {moved}"
    assert any(p.startswith("/x/s") for p in out)
    assert any(p.startswith("/x/l") for p in out)
    assert "/gone: key gone" in out and "/new: new key" in out
    nan = float("nan")
    assert _walk_diff({"n": 0.5}, {"n": nan}, "", []) == ["/n: 0.5 -> nan"]
    assert _walk_diff({"n": nan}, {"n": nan}, "", []) == []


# ------------------------------------------------------------- the reports

def test_replay_check_reports_the_same_report():
    """`replay --check` returns 1 whether or not anything is wrong: 52 of 52
    values present and rc=1, both before damage and after. The return code
    carries no signal here, only the report does."""
    _report("replay-annopage",
            ["replay", "--check", "bench/annopage/detect/PP-DocLayoutV2"],
            ["bench/annopage/detect/PP-DocLayoutV2/run.json"])


def test_the_table_reports_the_same_report():
    """Every applicable metric on one run, as one text. The run is NAMED, or
    the report would depend on how many models happen to be built here; the
    JSON goes to the bin so that the report is the only thing compared."""
    _report("table-slovar",
            ["bench", "all", "bench/slovar", "--run", "PP-DocLayoutV2",
             "--json", os.devnull],
            ["bench/slovar/slovar.pdf",
             "bench/slovar/detect/PP-DocLayoutV2/pages", "bench/slovar/truth"])


def test_the_built_book_reports_the_same_swaps():
    """`books html` and `books apply` were read by no lock at all, and three of
    the seven defects a key migration left lived exactly there: three sheet
    counters frozen at zero, a dead CSS selector, and a file quietly dropped
    out of `assets/source`."""
    _report("apply-status", ["apply", "processed/ogneupory-vl2", "--status"],
            ["processed/ogneupory-vl2/assets/swaps.json"])
