"""Whole reports, kept verbatim, so a rename cannot pass by moving no number.

WHY NOT FIVE NUMBERS. The obvious acceptance for the translation was the five
headline figures -- 698/1232 found, 646 whole, 375 merged, 501 extra jumps,
89.4 % ink. They were tried against a real migration and they are blind:
renaming all 13 996 Cyrillic keys in `bench/annopage` and leaving the code
untouched moved not one of the five. Nor did stopping halfway, at 300 files of
600.

WHAT DID MOVE, in that same experiment, was elsewhere in the same report:

    на объекте вне замера: 350        -> the line disappeared entirely
    лишняя рамка: 110                 -> 460
    истина о порядке: не размечен 600 -> НЕ СКАЗАНО 600
    sha256 сверен: 94cf0349275b       -> sha256 не сверен: поля нет в слепке

Three hundred and fifty boxes the bench had excluded from scoring were quietly
charged to the model, and the distinction between "checked and equal" and "had
nothing to check with" collapsed -- the exact distinction the project keeps a
rule about. None of it was visible in a headline figure, and all of it was
visible in the text around them.

So the acceptance is the text. Every line of every report, compared verbatim.

WHY `bench/hard` AND NOT ONLY `bench/annopage`. AnnoPage annotates no text at
all, so the whole text half of the report is `НЕ РАЗМЕЧЕНЫ` there and stays
that way through any damage. `bench/hard` mixes 124 AnnoPage pages with 6
synthetic ones, and it is the only tracked bench where the caption "считано по
6 страницам из 130" exists to be lost.

WHY THESE FIVE COMMANDS. Together they touch every format the migration
rewrites: truth and detect pages (`score`), truth content (`text`), the run
snapshot (`replay`), and the user-facing surface (`--help`), which nothing else
in the suite reads at all.
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
    # broken PROBE. Measured: renaming the normalisation level `нет` to `none`
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
    "help": (["--help"], []),
}


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
# "(в слепке 1f3ac82a, в дереве 5b4afbfe)" to say the snapshot was taken with
# different code. That hash changes on every edit to `models/doclayout.py`,
# comments included, so during a translation it would redden this report
# constantly and get fixed by `--save`, which blesses the other 582 lines
# blind. The hash IN THE SNAPSHOT is kept: it is data, and it must not move.
# The hash of the file on disk is not what these reports are guarding.
_CLOCK = re.compile(r"^\[\d\d:\d\d:\d\d\] ", re.M)
_TREE_HASH = re.compile(r"(в дереве )[0-9a-f]{8,}")


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


def main(argv):
    if "--save" in argv:
        done, skipped = save()
        for name, n in done:
            print(f"  saved {name}: {n} lines")
        for name, gone in skipped:
            print(f"  SKIPPED {name}: missing {', '.join(gone)}")
        return 0
    rc = 0
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
