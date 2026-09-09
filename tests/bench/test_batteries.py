"""Every probe of every applicable metric, on the drawn bench.

A number is not to be trusted until it has been shown able to fall. The run is
TRUTH ITSELF as the stand-in model: a known perfect score, which every probe
must lower -- and a probe that cannot lower a perfect answer measures nothing
anywhere.

The probes are built at collection, so each one is its own case with its own
name: a battery reporting one number for thirty probes says nothing about which
of them went silent, and a silent probe is where breakage looks like health.
`None` is "nothing to grip on this book" and is a skip, never a pass.
"""
import pytest
from conftest import slovar_bench

from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Run
from booksmith.datasets.metrics import base

BENCH = slovar_bench()
RUN = Run.bare(BENCH.truth_dir, "truth")
FIT = base.applicable(registry.METRICS, BENCH, RUN, BENCH.pages(), RUN.pages())
BUILT = {m.name: m.probes(BENCH, RUN) for m in FIT}

# What each metric had when the probes were counted here. A floor, not an exact
# count: a metric may grow a probe, and losing one is what this notices.
LEAST = {"contour": 34, "fitness": 32, "text": 29, "assembly": 3, "reading": 6}

PARAMS = [pytest.param(p, id=f"{name}-{p.name}")
          for name, ps in sorted(BUILT.items()) for p in ps]


def test_every_metric_the_drawn_bench_reaches_is_probed():
    """A metric absent from the run is a battery nobody notices missing."""
    assert set(BUILT) == set(LEAST) | {"snapshot"}, sorted(BUILT)


@pytest.mark.parametrize("name,least", sorted(LEAST.items()))
def test_the_metric_keeps_the_probes_it_had(name, least):
    got = len(BUILT[name])
    assert got >= least, (
        f"{name} has {got} probes and had {least}: a probe was struck out, "
        f"not added")


def test_the_snapshot_metric_has_nothing_to_knock_out_on_a_bare_run():
    """Truth as a stand-in model writes no `run.json`, so there is no required
    key to cut and the honest probe list is empty. That the check itself can
    fail is `tests/contract/test_snapshot.py`, on a snapshot built by hand."""
    assert BUILT["snapshot"] == [], BUILT["snapshot"]


@pytest.mark.parametrize("probe", PARAMS)
def test_the_probe_moves_the_number(probe):
    ok = probe.fn()
    note = ""
    if isinstance(ok, tuple):
        ok, note = ok
    if ok is None:
        pytest.skip("no data")
    assert ok, f"{probe.name}: {probe.want}" + (f" [{note}]" if note else "")
