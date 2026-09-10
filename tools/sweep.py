"""Every layout model over every bench, and the metrics of each, as one job.

A script and not a shell loop because it has to be resumable, has to say what
it skipped and why, and keeps each run's log beside the run: 6 models x 9
benches is 54 detections and hours of this CPU. A run it means to replace is
removed first -- `books detect` refuses to write a different experiment, which
is right for a person typing it and wrong for a tool that re-measures. Nothing
here spends money: every model is ONNX on the CPU.

Commit before measuring: a result stamped `<sha>+dirty tree` cannot be traced to
code and is never "already measured", while the stamp ignores what a measuring
pass writes (`stamp.OUTPUT_PATHS`), so a pass does not un-measure itself.

    python3 tools/sweep.py                 what would run
    python3 tools/sweep.py --apply         run it
    python3 tools/sweep.py --apply --books slovar,katalog --models yolox
    python3 tools/sweep.py --apply --again          re-detect and re-measure
    python3 tools/sweep.py --apply --metrics-only   re-measure, keep the boxes
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# (name for the log, the knobs that select it). The label a run lands under is
# the model's own (`Detector.label()`), never this name.
MODELS = (
    ("PP-DocLayoutV2", {"LAYOUT_ADAPTER": "doclayout",
                        "LAYOUT_MODEL_NAME": "PP-DocLayoutV2"}),
    ("PP-DocLayoutV3", {"LAYOUT_ADAPTER": "doclayout",
                        "LAYOUT_MODEL_NAME": "PP-DocLayoutV3"}),
    ("PP-DocLayout_plus-L", {"LAYOUT_ADAPTER": "doclayout",
                             "LAYOUT_MODEL_NAME": "PP-DocLayout_plus-L"}),
    ("docling-heron", {"LAYOUT_ADAPTER": "docling"}),
    ("docling-egret", {"LAYOUT_ADAPTER": "docling-egret"}),
    ("yolox", {"LAYOUT_ADAPTER": "yolox"}),
)

BOOKS = ("slovar", "katalog", "matematika", "atlas", "zhurnal", "spravochnik",
         "hard", "annopage")


def _books(root):
    """Bench directories that are books: a manifest and a scan beside it."""
    out = []
    for name in BOOKS:
        d = os.path.join(root, "bench", name)
        if not os.path.isfile(os.path.join(d, "manifest.json")):
            print(f"  SKIP {name}: no manifest.json -- not a book directory")
            continue
        with open(os.path.join(d, "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
        pdf = os.path.join(d, (man.get("source") or {}).get("name") or "")
        if not os.path.isfile(pdf):
            print(f"  SKIP {name}: {os.path.basename(pdf)} is not here "
                  f"(build it: books synth --book {name})")
            continue
        out.append((name, d))
    return out


def _read_runs(root):
    """(book, directory, label) for every level-two run on disk.

    Found by walking `processed/`, not by a list: `BOOKS` above says what to
    detect, which is a different question. A book with no `read/` contributes
    nothing and is not mentioned.
    """
    out = []
    base = os.path.join(root, "processed")
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = os.path.join(base, name)
        reads = os.path.join(d, "read")
        if not (os.path.isfile(os.path.join(d, "manifest.json"))
                and os.path.isdir(reads)):
            continue
        for label in sorted(os.listdir(reads)):
            if os.path.isdir(os.path.join(reads, label, "pages")):
                out.append((name, d, label))
    return out


def label_of(env):
    """Ask the adapter its label, before any page is read."""
    from booksmith.processing.layout import detect
    old = {k: os.environ.get(k) for k in env}
    try:
        os.environ.update(env)
        return detect._adapter().label()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.update({k: v})


def _has_pages(bdir, label) -> bool:
    """Boxes on disk that were cut from this book's scan.

    A directory is not boxes -- git creates one to hold a tracked `run.json` --
    and boxes cut from another file are worse than none. Neither is "already
    done", so the scan's sha256 has to match the manifest's.
    """
    run = os.path.join(bdir, "detect", label)
    d = os.path.join(run, "pages")
    if not (os.path.isdir(d) and any(n.endswith(".json")
                                     for n in os.listdir(d))):
        return False
    try:
        with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
            was = (json.load(f).get("source") or {}).get("sha256")
        with open(os.path.join(bdir, "manifest.json"), encoding="utf-8") as f:
            now = (json.load(f).get("source") or {}).get("sha256")
    except (OSError, ValueError):
        return False
    return bool(was) and was == now


def _measured(bdir, bname, label) -> bool:
    """Numbers on disk, taken by this tree.

    A results file from another commit is not a measurement of this code, which
    is what the header in it is for.
    """
    from booksmith.core import stamp
    p = os.path.join(ROOT, "results", f"{bname}-{label}.json")
    if not (os.path.isfile(p) and _has_pages(bdir, label)):
        return False
    # The same `ignore` the writer used, or this never answers yes: `table.py`
    # stamps a result with `commit(ignore=OUTPUT_PATHS)` precisely so that a
    # measuring pass cannot invalidate its own provenance. The two calls are one
    # decision and have to be spelt the same, or resume is dead.
    now = stamp.commit(ignore=stamp.OUTPUT_PATHS)
    if not now or "dirty" in now:
        # Nothing measured against an uncommitted tree counts as measured:
        # what produced it cannot be recovered.
        return False
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("commit") == now
    except (OSError, ValueError, AttributeError):
        return False


def _run(argv, env, logfile):
    """One command, its whole output kept beside the run it belongs to."""
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(argv)}\n")
        f.flush()
        r = subprocess.run(argv, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                           env={**os.environ, **env,
                                "PYTHONPATH": os.path.join(ROOT, "src")})
    return r.returncode


def main(argv):
    apply_ = "--apply" in argv
    # `--metrics-only` re-runs `bench all` and nothing else, over boxes that
    # are already there: a metric changes far more often than a detector, and a
    # sweep dirties the tree by rewriting the tracked snapshots. Hence the
    # recipe -- sweep, commit, re-measure from the clean tree -- and no hours of
    # detection spent again for the sake of a stamp.
    metrics_only = "--metrics-only" in argv
    again = "--again" in argv and not metrics_only
    want_b = _opt(argv, "--books")
    want_m = _opt(argv, "--models")
    books = [(n, d) for n, d in _books(ROOT) if not want_b or n in want_b]
    models = [(n, e) for n, e in MODELS if not want_m or n in want_m]
    if not books or not models:
        print("  nothing selected")
        return 1

    todo, skip, broken = [], [], []
    for mname, env in models:
        try:
            label = label_of(env)
        except Exception as e:
            # Named and skipped, not the end of the plan: one missing weights
            # file must not throw away the other models' work, and the run says
            # at the end which model never ran.
            broken.append((mname, f"{type(e).__name__}: {str(e)[:110]}"))
            continue
        for bname, bdir in books:
            # The skip is decided by the measurement and not by the boxes: a
            # directory git created to hold a tracked `run.json` has no pages
            # beside it, and a skip that covers `bench all` too leaves cells
            # with boxes and no numbers.
            done = _measured(bdir, bname, label)
            if metrics_only and not _has_pages(bdir, label):
                # No boxes to measure. Named, not silently skipped: a cell
                # missing from the table is not a result about the model.
                skip.append((bname, f"{label} (no boxes; detect it first)"))
                continue
            if done and not again and not metrics_only:
                skip.append((bname, label))
            else:
                todo.append((bname, bdir, mname, label, env,
                             _has_pages(bdir, label)))
    for m, why in broken:
        print(f"  CANNOT BUILD {m}: {why}")
    for b, l in skip:
        print(f"  have  {b:<14} {l}")
    for b, _, m, l, _e, has in todo:
        print(f"  {'again' if has else 'run  '} {b:<14} {l}"
              + (f"   ({m})" if m != l else "")
              + ("   (boxes are there; measuring only)" if has else ""))
    print(f"\n  {len(todo)} to run, {len(skip)} already there")
    if not apply_:
        print("  --apply to run, --again to redo what is there")
        return 0

    logs = os.path.join(ROOT, "results", "logs")
    os.makedirs(logs, exist_ok=True)
    started = time.time()
    failed = []
    for i, (bname, bdir, _mname, label, env, has) in enumerate(todo, 1):
        log = os.path.join(logs, f"{bname}-{label}.log")
        open(log, "w", encoding="utf-8").close()
        t0 = time.time()
        print(f"  [{i}/{len(todo)}] {bname} {label} ... ", end="", flush=True)
        if metrics_only:
            rc = 0
        elif not has or again:
            # The old run is removed before the new one, and by this tool
            # rather than by the command: `books detect` refuses to write a
            # different experiment, or one it cannot compare, which is right
            # for a person typing it and wrong for a sweep that re-measures.
            old_run = os.path.join(bdir, "detect", label)
            if os.path.isdir(old_run):
                shutil.rmtree(old_run)
                with open(log, "a", encoding="utf-8") as f:
                    f.write(f"# removed the previous run at {old_run}\n")
            rc = _run([sys.executable, "-m", "booksmith.cli", "detect", bdir],
                      env, log)
        else:
            rc = 0
        if rc:
            print(f"DETECT FAILED rc={rc}, see {os.path.relpath(log, ROOT)}")
            failed.append((bname, label, "detect", rc))
            continue
        rc = _run([sys.executable, "-m", "booksmith.cli", "bench", "all",
                   bdir, "--run", label], env, log)
        took = time.time() - t0
        if rc:
            print(f"METRICS FAILED rc={rc}, see {os.path.relpath(log, ROOT)}")
            failed.append((bname, label, "bench all", rc))
            continue
        print(f"{took:6.1f}s")
    # The level-two runs: `BOOKS` names directories under `bench/`, while
    # `processed/` is where the runs that have read anything live. The renderer
    # refuses a table whose cells come from two commits, so these ride in this
    # pass or are measured by nobody. Nothing is detected here -- the boxes
    # exist already and cost a rented card -- only measured.
    for bname, bdir, label in _read_runs(ROOT):
        t0 = time.time()
        print(f"  {bname:22} read/{label:28} ", end="", flush=True)
        log = os.path.join(logs, f"{bname}-read-{label}.log")
        rc = _run([sys.executable, "-m", "booksmith.cli", "bench", "all",
                   bdir, "--kind", "read", "--run", label], dict(os.environ), log)
        if rc:
            print(f"METRICS FAILED rc={rc}, see {os.path.relpath(log, ROOT)}")
            failed.append((bname, label, "bench all --kind read", rc))
            continue
        print(f"{time.time() - t0:6.1f}s")
    print(f"\n  {len(todo) - len(failed)} of {len(todo)} done in "
          f"{(time.time() - started) / 60:.1f} min")
    for b, l, what, rc in failed:
        print(f"  FAILED {b} {l}: {what} rc={rc}")
    # A model that never built is a failure of the sweep, not a footnote: at
    # exit 0 a five-of-six sweep reads as a whole one, and the renderer draws
    # the missing model as a column of dots.
    return 1 if (failed or broken) else 0


def _opt(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return {x.strip() for x in argv[i + 1].split(",") if x.strip()}
        if a.startswith(name + "="):
            return {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
