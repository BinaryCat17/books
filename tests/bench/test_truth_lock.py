"""The drawn truth, by sha256, against the bench built here and now.

The lock was written to prove that moving the generator changed no truth, and
it did prove it -- by hand, twice. A lock checked by hand is checked until
someone forgets, and then it is a file that agrees with nothing. It is read
here, so a generator change that moves the truth says so in the suite rather
than in a number three steps later.
"""
import hashlib
import os

from booksmith.core.config import ROOT

LOCK = os.path.join(ROOT, "tests", "expected", "slovar-truth.sha256")


def test_the_slovar_truth_lock_still_matches_the_bench_the_generator_draws(slovar):
    want = [ln.split("  ", 1) for ln in
            open(LOCK, encoding="utf-8").read().splitlines() if ln.strip()]
    assert want, f"{LOCK} is empty -- a lock over nothing"
    bad = []
    for digest, rel in want:
        fp = os.path.join(slovar.root, rel)
        if not os.path.exists(fp):
            bad.append(f"{rel}: gone")
            continue
        got = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if got != digest:
            bad.append(f"{rel}: {got[:12]} against {digest[:12]}")
    assert not bad, (
        f"the drawn truth moved from its lock ({len(bad)} of {len(want)} "
        f"files): {bad[:5]}. If the generator was MEANT to change, re-take the "
        f"lock: cd bench/slovar && sha256sum truth/*.json > "
        f"../../tests/expected/slovar-truth.sha256")
