"""Fixtures the suite shares: the synthetic bench, built once.

`bench/slovar` is untracked, so a check that needs truth builds its own copy
here instead of reading the tree. The build takes seconds and is memoised for
the whole session, because `tests/bench/test_batteries.py` needs the probe
list at collection time, before any fixture has run.
"""
import atexit
import shutil
import tempfile

import pytest

from booksmith.core import knobs
from booksmith.datasets.bench import Bench, Run
from booksmith.datasets.make import synth

_BUILT = {}


def slovar_bench(out=None) -> Bench:
    """The `slovar` bench, drawn with the knob defaults the CLI uses."""
    if "bench" not in _BUILT:
        d = str(out) if out is not None else tempfile.mkdtemp(prefix="slovar-")
        if out is None:
            atexit.register(shutil.rmtree, d, ignore_errors=True)
        synth.build(d, None, knobs.number("SYNTH_SEED", kind=int),
                    knobs.knob("SYNTH_AGING"), book="slovar",
                    log=lambda *_a: None)
        _BUILT["bench"] = Bench.open(d)
    return _BUILT["bench"]


@pytest.fixture(scope="session")
def slovar(tmp_path_factory):
    return slovar_bench(tmp_path_factory.mktemp("slovar"))


@pytest.fixture(scope="session")
def slovar_run(slovar):
    """Truth as the stand-in model: a perfect score every probe must lower."""
    return Run.bare(slovar.truth_dir, "truth")
