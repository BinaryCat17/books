"""`bench/<book>/detect/` becomes `bench/<book>/detect/<label>/`.

THE MOVE AS A TABLE, not as a walk with rules in it. Every source is named,
its destination is computed from the snapshot it already carries, and a
destination that already exists stops the whole script -- two runs merged into
one directory is the accident the labels exist to prevent, and it must not be
introduced by the migration that creates them.

`git mv` for tracked files so the rename is visible in the index; a plain move
for the untracked pages, which are large and local. A sha256 list is taken
before and compared after, over every file that moves.

    python3 tools/migrate_runs.py            what would move
    python3 tools/migrate_runs.py --apply    move it
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plan():
    """(source, destination) for every detect run that is not under a label."""
    out = []
    for run in sorted(glob.glob(os.path.join(ROOT, "bench", "*", "detect"))):
        snap = os.path.join(run, "run.json")
        if not os.path.isfile(snap):
            continue                      # already migrated, or not a run
        with open(snap, encoding="utf-8") as f:
            d = json.load(f)
        # The label the run already declares, else the model out of its own
        # fingerprint. NEVER the adapter name: one adapter serves three models.
        label = d.get("label") or (d.get("fingerprint") or {}).get("model")
        if not label:
            raise SystemExit(
                f"{snap}: neither `label` nor `fingerprint.model` -- this "
                f"snapshot cannot say which model wrote it, and a run filed "
                f"under a guessed name is a measurement against the wrong "
                f"model.")
        out.append((run, os.path.join(run, label)))
    return out


def _hashes(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            out[os.path.relpath(p, root)] = hashlib.sha256(
                open(p, "rb").read()).hexdigest()
    return out


def _tracked(path):
    r = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main(argv):
    moves = plan()
    if not moves:
        print("  nothing to move: every detect run is already under a label")
        return 0
    for src, dst in moves:
        if os.path.exists(dst):
            print(f"  REFUSED {dst} exists already -- two runs would merge "
                  f"into one directory")
            return 1
        rel = os.path.relpath(src, ROOT)
        print(f"  {rel}/* -> {os.path.relpath(dst, ROOT)}/  "
              f"({len(_hashes(src))} files)")
    if "--apply" not in argv:
        print("\n  --apply to move")
        return 0
    for src, dst in moves:
        was = _hashes(src)
        tmp = src + ".moving"
        os.rename(src, tmp)
        os.makedirs(src)
        os.rename(tmp, dst)
        # The one tracked file of a detect run: tell git, so the rename shows
        # in the index rather than as a delete and an add.
        snap_rel = os.path.relpath(os.path.join(src, "run.json"), ROOT)
        if _tracked(snap_rel):
            subprocess.run(["git", "add", "-A", os.path.relpath(src, ROOT)],
                           cwd=ROOT, check=True)
        now = _hashes(dst)
        if now != was:
            print(f"  BYTES MOVED in {dst}: "
                  f"{sorted(set(was) ^ set(now))[:5] or 'contents differ'}")
            return 1
        print(f"  moved {os.path.relpath(dst, ROOT)}: {len(now)} files, "
              f"every one byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
