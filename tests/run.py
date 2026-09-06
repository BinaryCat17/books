"""The check runner: no network, no GPU, no rentals.

    .venv/bin/python tests/run.py              every check
    .venv/bin/python tests/run.py --selfcheck  the mutation battery
    .venv/bin/python tests/run.py --slow       the slow ones too
    .venv/bin/python tests/run.py test_swap    one file

There is NO pytest in `.venv`, hence a runner of our own -- but the checks are
written so pytest would collect them unchanged: files `test_*.py`, functions
`test_*`, a plain `assert`.

IT PRINTS THE QUANTITY, NOT THE WORD "DONE": how many passed, how many failed,
how many were SKIPPED and why, and how many seconds it took. A skip is a
number of its own on purpose -- a zero from a check and a zero from not
understanding are different zeros, and "skipped 5" is as visible in the
summary line as a failure.

`--selfcheck` is the same thought as `metrics.mutations()`: a check must be
able to fail. The battery breaks the place under test (in memory, or in a COPY
of the source -- the working tree is never touched) and demands that the named
check go red. A mutation nobody caught prints as UNCAUGHT and fails the run: a
green check over broken code is worse than no check at all.
"""
import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import support                                              # noqa: E402
from support import Skip                                    # noqa: E402

# THIS RUNNER DECLARES ITSELF, and does so before the first check file is
# loaded. `support.skip()` chooses the form of a skip by WHO IS RUNNING; it
# used to choose by what is INSTALLED ("does pytest import"), and that would
# have cost a whole run -- see `support.foreign_skip`.
support.OWN_RUNNER = True

SLOW = "BOOKSMITH_TESTS_SLOW"


def load(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def files(only):
    out = []
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py"):
            if only and not any(o in fn for o in only):
                continue
            out.append(os.path.join(HERE, fn))
    return out


def cases(mod):
    return [(n, getattr(mod, n)) for n in sorted(vars(mod))
            if n.startswith("test_") and callable(getattr(mod, n))]


def run_case(fn):
    """(state, reason or traceback). Three states, and they differ."""
    try:
        fn()
        return "ok", ""
    except Skip as e:
        return "skip", str(e)
    except (Exception, SystemExit):
        # SystemExit is not an Exception: an adapter's refusal ("no docling
        # package", "unknown mode") arrives as exactly that, and swallowing it
        # would kill the runner instead of printing a failure.
        return "fail", traceback.format_exc()
    except BaseException as e:
        # Anything that is neither Exception nor SystemExit: a foreign skip
        # counts as a skip, everything else (KeyboardInterrupt, MemoryError)
        # goes out -- swallowing Ctrl+C would make the runner unstoppable.
        #
        # What counts as a foreign skip is decided in ONE place, `support`,
        # beside our own `Skip`. It is called through the module and not by
        # name: the battery breaks the place under test IN MEMORY, and without
        # that seam the probe "the runner does not know a foreign skip" could
        # not be applied at all.
        if support.foreign_skip(e):
            return "skip", f"{e} (declared through pytest.skip)"
        raise


def main(argv):
    only = [a for a in argv if not a.startswith("-")]
    if "--slow" in argv:
        os.environ[SLOW] = "1"
    t0 = time.time()
    ok = failed = skipped = 0
    bad, skips = [], []
    for path in files(only):
        mod = load(path)
        base = os.path.basename(path)
        for name, fn in cases(mod):
            t = time.time()
            state, why = run_case(fn)
            dt = time.time() - t
            mark = {"ok": "  ", "skip": "  SKIP", "fail": "  FAIL"}[state]
            print(f"{mark} {base}::{name}  {dt:.3f}s"
                  + (f"  -- {why}" if state == "skip" else ""))
            if state == "ok":
                ok += 1
            elif state == "skip":
                skipped += 1
                skips.append(f"{base}::{name} -- {why}")
            else:
                failed += 1
                bad.append((f"{base}::{name}", why))
    for name, tb in bad:
        print(f"\n--- FAIL {name} ---\n{tb}")
    print(f"\nchecks {ok + failed + skipped}: passed {ok}, failed "
          f"{failed}, skipped {skipped}; {time.time() - t0:.1f}s")
    if skipped and not bad:
        print("what was SKIPPED is checked by nothing: " + "; ".join(skips))
    rc = 1 if failed else 0
    if "--selfcheck" in argv:
        import selfcheck
        rc = selfcheck.main() or rc
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
