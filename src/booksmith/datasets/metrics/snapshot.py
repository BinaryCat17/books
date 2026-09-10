"""The snapshot metric: is a run's `run.json` complete, as a `Record`.

The check of `core.replay`, published as scalars, so a run whose snapshot is
hollow is visible where its numbers are. Needs pages and a snapshot: a bare
run (`Run.bare`) has nothing to check and says so.
"""
from booksmith.core import replay
from booksmith.datasets.metrics.base import Metric, Record, Scalar, Spec


class SnapshotMetric(Metric):
    name = "snapshot"
    needs = frozenset({"pages"})
    scalars = (
        Spec("values_present", "neither",
             "keys present in the snapshot"),
        Spec("missing", "lower",
             "keys the snapshot lacks"),
        Spec("empty", "lower",
             "knob values empty in the snapshot"),
        Spec("fingerprint_verified", "neither",
             "1 if the fingerprint was verified against the tree, 0 if not"),
    )

    def _record(self, bench_name, run) -> Record:
        if run.run_dir is None:
            why = "a bare page directory: no run.json to check"
            scalars = {"values_present": Scalar(None, why=why),
                       "missing": Scalar(None, why=why),
                       "empty": Scalar(None, why=why),
                       "fingerprint_verified": Scalar(None, why=why)}
            return Record(self.name, bench_name, run.label, scalars, {}, {})
        snap = replay.facts(run.run_dir)
        sh = replay.shape(snap)
        req = replay.required(snap, sh)
        miss = replay.missing(snap, req)
        hol = replay.hollow(snap, req)
        n_req = len(req)
        verified = None if sh.get("blind") or sh.get("not_derived") else (
            0 if sh.get("not_verified") else 1)
        scalars = {
            "values_present": Scalar(n_req - len(miss), count=(n_req - len(miss), n_req)),
            "missing": Scalar(len(miss), count=(len(miss), n_req)),
            "empty": Scalar(len(hol), count=(len(hol), n_req)),
            "fingerprint_verified": Scalar(
                verified, why=None if verified is not None else
                ("the fingerprint was not verified at all" if sh.get("blind")
                 else "the fingerprint shape would not derive")),
        }
        detail = {"required": n_req, "missing": [list(map(str, p)) for p, _ in miss],
                  "empty": [list(map(str, p)) for p, _ in hol], "shape": sh.get("row")}
        return Record(self.name, bench_name, run.label, scalars, {}, detail)

    def run(self, bench, run) -> Record:
        return self._record(bench.name if bench is not None else "", run)

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        return self._record(bench.name if bench is not None else "", run)

    def report(self, rec: Record, log=print) -> None:
        for k, s in rec.scalars.items():
            log(f"{k}: {s.value if s.value is not None else s.why}")
