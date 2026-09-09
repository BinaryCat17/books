"""Probes of the snapshot metric: cut each required key out and see it noticed.

One probe per required key. A key the snapshot never had cannot be knocked out
and says so as "no data": that trouble is the WRITER's and is a scalar of the
record, not a failure of the check.
"""
import json

from booksmith.core import replay
from booksmith.datasets.metrics.base import Probe


def _cut(snap, req, path):
    cut = json.loads(json.dumps(snap))
    cur = cut
    for k in path[:-1]:
        cur = cur[k]
    del cur[path[-1]]
    return any(p == path for p, _ in replay.missing(cut, req))


def probes(bench, run) -> list:
    if run.run_dir is None:
        return []
    snap = replay.facts(run.run_dir)
    if not snap:
        return []
    req = replay.required(snap, replay.shape(snap))
    out = []
    for path, what in req:
        key = "/".join(map(str, path))
        out.append(Probe(
            f"{key} cut from the snapshot", f"the check names it missing -- {what}",
            (lambda p=path: None if not replay._dig(snap, p)[0]
             else _cut(snap, req, p))))
    return out
