"""Every layout model over every bench, and the metrics of each, as one job.

WHY A SCRIPT AND NOT A SHELL LOOP. It has to be resumable, it has to say what
it skipped and why, and it has to keep the log of each run beside the run --
6 models x 9 benches is 54 detections and 3.6 hours on this CPU, and a loop
that dies at 40 with the reason on a scrolled-off terminal has to start again.

WHAT IT DOES NOT DO: it never deletes a run. A model whose directory is
already there is SKIPPED and said so; `--again` re-runs it. Nothing here
spends money -- every model is ONNX on the CPU, and the reading models are not
in this table.

    python3 tools/sweep.py                 what would run
    python3 tools/sweep.py --apply         run it
    python3 tools/sweep.py --apply --books slovar,katalog --models yolox
    python3 tools/sweep.py --apply --again      re-run what is already there
"""
import json
import os
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
         "hard36", "hard", "annopage")


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
    again = "--again" in argv
    want_b = _opt(argv, "--books")
    want_m = _opt(argv, "--models")
    books = [(n, d) for n, d in _books(ROOT) if not want_b or n in want_b]
    models = [(n, e) for n, e in MODELS if not want_m or n in want_m]
    if not books or not models:
        print("  nothing selected")
        return 1

    todo, skip = [], []
    for mname, env in models:
        try:
            label = label_of(env)
        except Exception as e:
            print(f"  CANNOT BUILD {mname}: {type(e).__name__}: "
                  f"{str(e)[:120]}")
            return 1
        for bname, bdir in books:
            dst = os.path.join(bdir, "detect", label)
            if os.path.isdir(dst) and not again:
                skip.append((bname, label))
            else:
                todo.append((bname, bdir, mname, label, env))
    for b, l in skip:
        print(f"  have  {b:<14} {l}")
    for b, _, m, l, _e in todo:
        print(f"  run   {b:<14} {l}" + (f"   ({m})" if m != l else ""))
    print(f"\n  {len(todo)} to run, {len(skip)} already there")
    if not apply_:
        print("  --apply to run, --again to redo what is there")
        return 0

    logs = os.path.join(ROOT, "bench", "results", "logs")
    os.makedirs(logs, exist_ok=True)
    started = time.time()
    failed = []
    for i, (bname, bdir, mname, label, env) in enumerate(todo, 1):
        log = os.path.join(logs, f"{bname}-{label}.log")
        open(log, "w", encoding="utf-8").close()
        t0 = time.time()
        print(f"  [{i}/{len(todo)}] {bname} {label} ... ", end="", flush=True)
        rc = _run([sys.executable, "-m", "booksmith.cli", "detect", bdir],
                  env, log)
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
    print(f"\n  {len(todo) - len(failed)} of {len(todo)} done in "
          f"{(time.time() - started) / 60:.1f} min")
    for b, l, what, rc in failed:
        print(f"  FAILED {b} {l}: {what} rc={rc}")
    return 1 if failed else 0


def _opt(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return {x.strip() for x in argv[i + 1].split(",") if x.strip()}
        if a.startswith(name + "="):
            return {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
