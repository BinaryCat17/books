"""Every probe of every applicable metric, on the drawn bench.

The run is truth itself as the stand-in model: a perfect score which every
probe must lower, and a probe that cannot lower a perfect answer measures
nothing anywhere.

The probes are built at collection, so each one is a case with its own name
and a probe gone silent is visible. `None` is "nothing to grip on this book"
and is a skip, never a pass.
"""
import pytest
from conftest import slovar_bench, tree_detect_run

from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Run
from booksmith.datasets.metrics import base

# Built at collection so each probe is a case of its own. A build or probe
# failure skips this module and nothing else.
try:
    BENCH = slovar_bench()
    RUN = Run.bare(BENCH.truth_dir, "truth")
    FIT = base.applicable(registry.METRICS, BENCH, RUN, BENCH.pages(), RUN.pages())
    BUILT = {m.name: m.probes(BENCH, RUN) for m in FIT}
except Exception as e:
    pytest.skip(f"the drawn bench could not be built or probed: {e}", allow_module_level=True)

# A floor, not an exact count: a metric may grow a probe; losing one fails here.
LEAST = {"contour": 34, "fitness": 32, "text": 29, "assembly": 3, "reading": 6}

PARAMS = [pytest.param(p, id=f"{name}-{p.name}")
          for name, ps in sorted(BUILT.items()) for p in ps]

# The same probes over a real detect run, where the tree holds one.
_TREE = tree_detect_run()
if _TREE is not None:
    _B2, _R2 = _TREE
    _FIT2 = base.applicable(registry.METRICS, _B2, _R2, _B2.pages(), _R2.pages())
    PARAMS += [pytest.param(p, id=f"{m.name}-{p.name}[{_R2.label}]")
               for m in _FIT2 for p in m.probes(_B2, _R2)]


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
    fail is tests/contract/test_snapshot.py."""
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


@pytest.mark.parametrize("name,scalar,want", [
    ("contour", "artefacts_found", 1.0), ("contour", "text_furniture_found", 1.0),
    ("contour", "model_order", 1.0), ("contour", "label_errors", 0),
    ("text", "CER", 0.0), ("text", "paired", 1.0),
])
def test_truth_against_itself_is_the_perfect_score(name, scalar, want):
    """The baseline every probe lowers: without it a probe proves only a fall."""
    rec = registry.BY_NAME[name].run(BENCH, RUN)
    got = rec.scalars[scalar].value
    assert got == want, f"{name}.{scalar} on truth against truth is {got}, not {want}"
