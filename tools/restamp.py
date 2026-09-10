"""Re-stamp the identity of run snapshots after the rule for it moved.

    python tools/restamp.py bench/*/detect/*/run.json

The identity is recomputed from what the snapshot already holds -- its
fingerprint and the knob values it read -- by today's `stamp.identity`, and
the file is rewritten only where the hash moved. Nothing else in the file
changes. Run once, when a knob leaves or joins `KNOBS_NOT_IDENTITY`: without
it `guard_identity` refuses every future run beside the tracked ones.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from booksmith.core import stamp
from booksmith.core.page import write_json


def restamp(path: str) -> tuple[str, str]:
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    old = snap.get("identity") or ""
    new = stamp.identity(snap.get("fingerprint") or {}, stamp.knob_values(snap))
    if new != old:
        snap["identity"] = new
        write_json(path, snap, indent=1)
    return old, new


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 64
    moved = 0
    for path in argv:
        old, new = restamp(path)
        if old != new:
            moved += 1
        print(f"{'moved   ' if old != new else 'unchanged'} {path}: "
              f"{old[:12] or '(none)'} -> {new[:12]}")
    print(f"{len(argv)} snapshots, {moved} moved")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
