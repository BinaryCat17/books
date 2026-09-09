"""Fixtures the suite shares: the synthetic bench, built once per session.

`bench/slovar` is untracked, so a check that needs truth builds its own copy
here. The build is memoised because tests/bench/test_batteries.py needs the
probe list at collection time, before any fixture has run.
"""
import atexit
import os
import shutil
import tempfile

import pytest

from booksmith.core import config, knobs
from booksmith.datasets.bench import Bench, Run
from booksmith.datasets.make import synth

_BUILT = {}


def slovar_bench() -> Bench:
    """The `slovar` bench, drawn with the knob defaults the CLI uses."""
    if "bench" not in _BUILT:
        d = tempfile.mkdtemp(prefix="slovar-")
        atexit.register(shutil.rmtree, d, ignore_errors=True)
        synth.build(d, None, knobs.number("SYNTH_SEED", kind=int),
                    knobs.knob("SYNTH_AGING"), book="slovar",
                    log=lambda *_a: None)
        _BUILT["bench"] = Bench.open(d)
    return _BUILT["bench"]


def tree_detect_run(label="PP-DocLayoutV2"):
    """The tracked tree's own `bench/slovar` with a real detect run, when this
    machine holds one; None on a clone."""
    root = os.path.join(config.ROOT, "bench", "slovar")
    run = os.path.join(root, "detect", label)
    if not (os.path.isdir(os.path.join(root, "truth")) and os.path.isfile(
            os.path.join(run, "run.json")) and os.path.isdir(os.path.join(run, "pages"))):
        return None
    return Bench.open(root), Run.open(run)


@pytest.fixture(scope="session")
def slovar():
    return slovar_bench()


@pytest.fixture(scope="session")
def slovar_run(slovar):
    """Truth as the stand-in model: a perfect score every probe must lower."""
    return Run.bare(slovar.truth_dir, "truth")
