"""Every layout model over every bench, and the metrics of each, as one job.

WHY A SCRIPT AND NOT A SHELL LOOP. It has to be resumable, it has to say what
it skipped and why, and it has to keep the log of each run beside the run --
6 models x 9 benches is 54 detections and 3.6 hours on this CPU, and a loop
that dies at 40 with the reason on a scrolled-off terminal has to start again.

WHAT IT DELETES, AND SAYS SO. A run it means to replace is REMOVED first --
`books detect` refuses to write a different experiment, or one it cannot
compare because the run there records no identity, and that refusal is right
for a person typing it. A tool whose job is to re-measure does the deletion
explicitly instead. This docstring said "it never deletes a run" for a while
after that stopped being true, including for the three TRACKED `run.json`
files. Nothing here spends money -- every model is ONNX on the CPU, and the
reading models are not in this table.

AND A DIRTY TREE IS NOT A MEASUREMENT. `stamp.commit()` returns
`<sha>+dirty tree` for any uncommitted state, so a result stamped that way
cannot be traced to code and is never "already measured" -- it is re-run. The
inverse mattered more: a CLEAN result at the same sha did not match a dirty
`stamp.commit()` and was re-measured INTO a dirty one. And the sweep dirties
the tree itself, by rewriting the tracked snapshots: measured mid-run, 6
results clean and 11 dirty, and the renderer refused all 17. Commit first --
though `results/` and `METRICS.md` are what a measuring pass WRITES, and both
the stamp and the question asked of it exclude them (`stamp.OUTPUT_PATHS`), so
the sweep no longer un-measures itself by running.

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
# the MODEL's own (`Detector.label()`), never this name: the two agree today
# and the day they do not, the model's answer is the one that decides.
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

    Found by walking `processed/`, not by a list: a book with a reading run
    is a thing that exists or does not, and the nine-name `BOOKS` tuple above
    is a list of what to DETECT, which is a different question. A book with
    no `read/` contributes nothing and is not mentioned.
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
    """Ask the ADAPTER its label, before any page is read."""
    from booksmith.processing.layout import detect
    old = {k: os.environ.get(k) for k in env}
    try:
        os.environ.update(env)
        return detect._adapter().label()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.update({k: v})


def _has_pages(bdir, label) -> bool:
    """Boxes on disk that were cut from THIS book's scan.

    A DIRECTORY is not boxes: git creates one to hold a tracked `run.json`,
    and the pages beside it are ignored, so `isdir` was true with nothing in
    it. And boxes cut from ANOTHER file are worse than none -- `bench/hard`
    was rebuilt today, so its migrated run measures a pdf that no longer
    exists, and `bench all` refuses it (rightly) with "DIFFERENT books".
    Neither case is "already done".
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
    """Numbers on disk, taken by THIS tree. A results file from another
    commit is not a measurement of this code -- that is what the header in it
    is for."""
    from booksmith.core import stamp
    p = os.path.join(ROOT, "results", f"{bname}-{label}.json")
    if not (os.path.isfile(p) and _has_pages(bdir, label)):
        return False
    # THE SAME `ignore` THE WRITER USED, or this never answers yes. `table.py`
    # stamps a result with `commit(ignore=OUTPUT_PATHS)` precisely so a
    # measuring pass cannot invalidate its own provenance -- and the reader
    # here asked the bare question, so the sweep's OWN first result dirtied
    # the tree and every later cell read as "not measured". Resume was dead
    # for as long as `results/` has been tracked: a 4-hour detection run that
    # died at cell 40 started again from one. The two calls are one decision
    # and have to be spelt the same.
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
    # `--metrics-only` RE-RUNS `bench all` AND NOTHING ELSE, over boxes that
    # are already there. It exists because a metric changes far more often
    # than a detector does, and because a sweep dirties the tree by rewriting
    # the tracked snapshots -- so the honest recipe is: sweep, commit, then
    # re-measure from the clean tree, and every cell carries one commit.
    # Three and a half hours of detection are not spent again for a stamp.
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
            # NAMED AND SKIPPED, not the end of the plan. Aborting on one
            # missing weights file threw away the other five models' worth of
            # work; the run says at the end which model never ran.
            broken.append((mname, f"{type(e).__name__}: {str(e)[:110]}"))
            continue
        for bname, bdir in books:
            # THE SKIP IS DECIDED BY THE MEASUREMENT, NOT BY THE BOXES.
            # `os.path.isdir(detect/<label>)` was the test, and it is true
            # for a directory git created to hold one tracked `run.json` with
            # NO PAGES beside it -- so on a fresh clone the three biggest
            # benches skipped the baseline model. Worse, the skip covered
            # `bench all` too, so nine cells of V2 had boxes and no numbers
            # and the table's baseline column was empty.
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
            # THE OLD RUN IS REMOVED BEFORE THE NEW ONE, and by this tool
            # rather than by the command. `books detect` refuses to write a
            # different experiment -- or one it cannot compare, which is
            # every run migrated from before identities existed -- and that
            # is right for a person typing it. A sweep whose job is to
            # re-measure says so out loud instead, here.
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
    # THE LEVEL-TWO RUNS, WHICH THIS SWEEP COULD NOT REACH. `BOOKS` names
    # nine directories under `bench/`, so `processed/` was invisible to it --
    # and `processed/` is where the only runs that have READ anything live.
    # Every scalar about reading was therefore measured by nobody, and the
    # renderer refuses a table whose cells come from two commits, so they
    # could not be added afterwards either: they had to ride in this pass or
    # not at all. Nothing is DETECTED here -- the boxes already exist and
    # cost a rented card -- only measured.
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
    # A MODEL THAT NEVER BUILT IS A FAILURE OF THE SWEEP, not a footnote. It
    # was printed and the exit code stayed 0, so a five-of-six sweep looked
    # like a whole one -- and the renderer then draws the missing model as a
    # column of dots.
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
