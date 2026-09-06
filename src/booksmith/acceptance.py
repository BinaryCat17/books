"""Whole reports, kept verbatim, so a rename cannot pass by moving no number.

WHY NOT FIVE NUMBERS. The obvious acceptance for the translation was the five
headline figures -- 698/1232 found, 646 whole, 375 merged, 501 extra jumps,
89.4 % ink. They were tried against a real migration and they are blind:
renaming all 13 996 Cyrillic keys in `bench/annopage` and leaving the code
untouched moved not one of the five. Nor did stopping halfway, at 300 files of
600.

WHAT DID MOVE, in that same experiment, was elsewhere in the same report:

    on an object outside scoring: 350 -> the line disappeared entirely
    spurious_box: 110                 -> 460
    truth on order: not marked 600    -> NOT SAID 600
    sha256 checked: 94cf0349275b      -> sha256 NOT checked: no such field

Three hundred and fifty boxes the bench had excluded from scoring were quietly
charged to the model, and the distinction between "checked and equal" and "had
nothing to check with" collapsed -- the exact distinction the project keeps a
rule about. None of it was visible in a headline figure, and all of it was
visible in the text around them.

So the acceptance is the text. Every line of every report, compared verbatim.

WHY `bench/hard` AND NOT ONLY `bench/annopage`. AnnoPage annotates no text at
all, so the whole text half of the report is `NOT MARKED` there and stays
that way through any damage. `bench/hard` mixes 124 AnnoPage pages with 6
synthetic ones, and it is the only tracked bench where the caption "counted
over 6 pages of 130" exists to be lost.

WHY THESE COMMANDS. Together they touch every format the migration
rewrites: truth and detect pages (`score`), truth content (`text`), the run
snapshot (`replay`), the built book (`apply --status`), the three probe
batteries (`--selfcheck`, whose probe NAMES are the only lock on them), and
the user-facing surface (`--help`), which nothing else in the suite reads at
all. The table started at five and grew as defects were found outside it.

THE RECORDS BESIDE THE REPORTS. A report is prose, and prose can be
rearranged without a number moving -- the instrument for that is `--numbers`.
The reverse also happens: a result dict grows a key no report prints, or a
key the report rounds. So `RECORDS` keeps the RAW RESULT DICTS of the three
metrics as JSON, floats rounded to six places, compared key by key at 1e-6,
each with the sha256 of the truth and manifest it was taken against. That is
the lock the package move is measured with: a metric moved to another file
must return the same dict to the last key.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPECTED = os.path.join(ROOT, "bench", "expected")

# name -> (argv after `books`, paths that must exist for it to run at all)
COMMANDS = {
    "score-annopage": (
        ["score", "bench/annopage/truth", "bench/annopage/detect/pages"],
        ["bench/annopage/truth", "bench/annopage/detect/pages"]),
    "score-hard": (
        ["score", "bench/hard/truth", "bench/hard/detect/pages"],
        ["bench/hard/truth", "bench/hard/detect/pages"]),
    "text-slovar": (
        ["text", "bench/slovar/truth", "bench/slovar/truth"],
        ["bench/slovar/truth"]),
    "replay-annopage": (
        ["replay", "--check", "bench/annopage/detect"],
        ["bench/annopage/detect/run.json"]),
    # `books text --selfcheck` is here because the reports alone cannot see a
    # broken PROBE. Measured: renaming the normalisation level to `none`
    # in one place and not the other made `--norm none` do exactly what
    # `boundary` does -- three levels became two -- and the probe that guarded
    # it threw instead of measuring. The report `text-slovar` was identical
    # throughout; only the battery line moved, from 0 uncaught to 1.
    "text-selfcheck": (
        ["text", "bench/slovar/truth", "bench/slovar/truth", "--selfcheck"],
        ["bench/slovar/truth"]),
    # The book is built and swapped by two commands that no report read at
    # all, and three of the seven defects the migration left lived exactly
    # there: three sheet counters stuck at zero, a dead CSS selector, and a
    # file silently dropped out of `assets/source`.
    "apply-status": (
        ["apply", "processed/ogneupory-vl2", "--status"],
        ["processed/ogneupory-vl2/assets/swaps.json"]),
    # The contour and fitness batteries had no lock at all: their probe names
    # were quoted in prose (33 and 21) and verified by nothing. `fitness` on
    # slovar returns 1 (one probe uncaught by construction, the dark column);
    # the report is compared as text and the code is not looked at.
    "score-selfcheck": (
        ["score", "bench/slovar/truth", "bench/slovar/detect/pages",
         "--selfcheck"],
        ["bench/slovar/truth", "bench/slovar/detect/pages"]),
    "fitness-selfcheck": (
        ["fitness", "bench/slovar/slovar.pdf", "--detect",
         "bench/slovar/detect/pages", "--truth", "bench/slovar/truth",
         "--selfcheck"],
        ["bench/slovar/slovar.pdf", "bench/slovar/detect/pages",
         "bench/slovar/truth"]),
    "help": (["--help"], []),
}

# name -> (how to compute the raw result dict, the inputs whose sha256 it is
# taken against, paths that must exist). Computed IN PROCESS, unlike the
# reports: the dict is the thing, not what a command prints about it.
RECORDS = {
    "score-annopage": (
        ("metrics", "compare", ["bench/annopage/truth",
                                "bench/annopage/detect/pages"]),
        ["bench/annopage/truth", "bench/annopage/manifest.json",
         "bench/annopage/detect/pages"]),
    "score-hard": (
        ("metrics", "compare", ["bench/hard/truth", "bench/hard/detect/pages"]),
        ["bench/hard/truth", "bench/hard/manifest.json",
         "bench/hard/detect/pages"]),
    "text-slovar": (
        ("text", "measure", ["bench/slovar/truth", "bench/slovar/truth"]),
        ["bench/slovar/truth", "bench/slovar/manifest.json"]),
    "fitness-slovar": (
        ("fitness", "measure", ["bench/slovar/slovar.pdf",
                                "bench/slovar/detect/pages",
                                "bench/slovar/truth"]),
        ["bench/slovar/slovar.pdf", "bench/slovar/truth",
         "bench/slovar/manifest.json", "bench/slovar/detect/pages"]),
}

TOLERANCE = 1e-6


def missing(name):
    """Paths this command needs that are not on disk. Empty means runnable.

    `bench/*/detect/pages` and the synthetic benches are behind .gitignore, so
    on a fresh clone most of these cannot run. That is a skip with a reason,
    never a pass: a check that silently measures nothing is the failure this
    whole file exists to prevent.
    """
    _, needs = COMMANDS[name]
    return [p for p in needs if not os.path.exists(os.path.join(ROOT, p))]


# TWO THINGS MOVE ON THEIR OWN AND ARE DROPPED BEFORE COMPARING.
#
# The wall clock on every log line, obviously.
#
# And the hash of a SOURCE file as it is right now -- `replay --check` prints
# "(snapshot 1f3ac82a, tree 5b4afbfe)" to say the snapshot was taken with
# different code. That hash changes on every edit to `models/doclayout.py`,
# comments included, so during a translation it would redden this report
# constantly and get fixed by `--save`, which blesses the other 582 lines
# blind. The hash IN THE SNAPSHOT is kept: it is data, and it must not move.
# The hash of the file on disk is not what these reports are guarding.
_CLOCK = re.compile(r"^\[\d\d:\d\d:\d\d\] ", re.M)
_TREE_HASH = re.compile(r"(tree )[0-9a-f]{8,}")


def run(name):
    """The command's output, verbatim but for the clock, stdout and stderr."""
    argv, _ = COMMANDS[name]
    # COLUMNS is pinned because argparse wraps the help to the terminal width:
    # at COLUMNS=40 the help report differed by 76 lines while nothing had
    # changed. A snapshot that depends on the window it was taken in is not a
    # snapshot.
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), COLUMNS="80")
    r = subprocess.run([sys.executable, "-m", "booksmith.cli"] + argv,
                       cwd=ROOT, capture_output=True, text=True, env=env)
    out = _CLOCK.sub("", r.stdout + r.stderr)
    return _TREE_HASH.sub(r"\1<current source>", out)


def path(name):
    return os.path.join(EXPECTED, name + ".txt")


def record_path(name):
    return os.path.join(EXPECTED, name + ".json")


def record_missing(name):
    _, inputs = RECORDS[name]
    return [p for p in inputs if not os.path.exists(os.path.join(ROOT, p))]


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


def _sha256_of_inputs(paths):
    """One hash over every input file, in a fixed order, so the record says
    what it was taken against and a rebuilt bench cannot pass as the same."""
    import hashlib
    h = hashlib.sha256()
    for rel in paths:
        p = os.path.join(ROOT, rel)
        files = ([p] if os.path.isfile(p) else
                 sorted(os.path.join(d, f) for d, _, fs in os.walk(p)
                        for f in fs))
        for f in files:
            h.update(os.path.relpath(f, ROOT).encode())
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def record(name):
    """{"inputs": sha256, "result": the raw dict} for one record, computed now."""
    import importlib
    (modname, fn, args), inputs = RECORDS[name]
    mod = importlib.import_module("booksmith." + modname)
    res = getattr(mod, fn)(*[os.path.join(ROOT, a) for a in args])
    return {"inputs": _sha256_of_inputs(inputs), "result": _clean(res)}


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
        if abs(want - got) > TOLERANCE:
            out.append(f"{at}: {want} -> {got}")
    elif want != got:
        out.append(f"{at}: {want!r} -> {got!r}")
    return out


def record_differs(name):
    """[] if the record matches its snapshot; else the differing paths.

    An input that moved is reported FIRST and alone: a record taken against
    other truth is not "changed", it is incomparable, and the two must not
    read alike.
    """
    import json
    with open(record_path(name), encoding="utf-8") as f:
        want = json.load(f)
    got = record(name)
    if want["inputs"] != got["inputs"]:
        return [f"INPUTS MOVED: the snapshot was taken against "
                f"{want['inputs'][:12]}, the tree holds {got['inputs'][:12]}"]
    return _walk_diff(want["result"], got["result"], "", [])


def save_records(names=None):
    import json
    os.makedirs(EXPECTED, exist_ok=True)
    done, skipped = [], []
    for name in names or RECORDS:
        gone = record_missing(name)
        if gone:
            skipped.append((name, gone))
            continue
        rec = record(name)
        with open(record_path(name), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        done.append((name, len(json.dumps(rec))))
    return done, skipped


def save(names=None):
    os.makedirs(EXPECTED, exist_ok=True)
    done, skipped = [], []
    for name in names or COMMANDS:
        gone = missing(name)
        if gone:
            skipped.append((name, gone))
            continue
        text = run(name)
        with open(path(name), "w", encoding="utf-8") as f:
            f.write(text)
        done.append((name, len(text.splitlines())))
    return done, skipped


def differs(name):
    """[] if the report matches its snapshot, else the differing lines."""
    import difflib
    want = open(path(name), encoding="utf-8").read().splitlines()
    got = run(name).splitlines()
    return [ln for ln in difflib.unified_diff(want, got, "expected", "now",
                                              lineterm="", n=1)]


NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def numbers_moved(name):
    """Numbers in the report that are not in the snapshot, and the reverse.

    THE INSTRUMENT THE TRANSLATION NEEDS. Once the report TEXT is being
    translated, `differs` fires on every line and the only honest question
    left is whether any MEASUREMENT moved. Compared as multisets, because
    renaming a bucket reorders an alphabetical list without changing a value:
    that reordering alone made a first attempt at this check report 1936
    differences where there were none.
    """
    import collections
    want = collections.Counter(NUMBER.findall(
        open(path(name), encoding="utf-8").read()))
    got = collections.Counter(NUMBER.findall(run(name)))
    return sorted((want - got).items()), sorted((got - want).items())


def main(argv):
    if "--numbers" in argv:
        rc = 0
        for name in COMMANDS:
            if missing(name) or not os.path.isfile(path(name)):
                print(f"  SKIPPED {name}")
                continue
            gone, came = numbers_moved(name)
            if gone or came:
                rc = 1
                print(f"  MOVED   {name}: lost {gone[:6]}, gained {came[:6]}")
            else:
                print(f"  same numbers  {name}")
        return rc
    if "--save" in argv:
        # `--save NAME...` saves only those; bare `--save` saves everything.
        # Naming them matters: a blanket save blesses every other report
        # blind, which is the failure `_TREE_HASH` above was written against.
        only = [a for a in argv if not a.startswith("--")]
        done, skipped = save([n for n in only if n in COMMANDS] or None
                             if only else None)
        for name, n in done:
            print(f"  saved {name}: {n} lines")
        for name, gone in skipped:
            print(f"  SKIPPED {name}: missing {', '.join(gone)}")
        wanted = [n for n in only if n in RECORDS]
        if not only or wanted:
            done, skipped = save_records(wanted or None)
            for name, n in done:
                print(f"  saved record {name}: {n} bytes")
            for name, gone in skipped:
                print(f"  SKIPPED record {name}: missing {', '.join(gone)}")
        return 0
    rc = 0
    for name in RECORDS:
        gone = record_missing(name)
        if gone:
            print(f"  SKIPPED record {name}: missing {', '.join(gone)}")
            continue
        if not os.path.isfile(record_path(name)):
            print(f"  NO RECORD {name}: run --save")
            rc = 1
            continue
        d = record_differs(name)
        if d:
            print(f"  CHANGED record {name}: {len(d)} paths")
            for ln in d[:20]:
                print("    " + ln)
            rc = 1
        else:
            print(f"  same record {name}")
    for name in COMMANDS:
        gone = missing(name)
        if gone:
            print(f"  SKIPPED {name}: missing {', '.join(gone)}")
            continue
        if not os.path.isfile(path(name)):
            print(f"  NO SNAPSHOT {name}: run --save")
            rc = 1
            continue
        d = differs(name)
        if d:
            print(f"  CHANGED {name}: {len(d)} diff lines")
            for ln in d[:20]:
                print("    " + ln)
            rc = 1
        else:
            print(f"  same    {name}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
