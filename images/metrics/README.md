# metrics

Every metric with its declaration and its probes, behind four routes. The
service is stateless and reads the storage volume.

Run: `python -m metrics` with `BOOKSMITH_HOME` and `BOOKSMITH_SCHEMA`.
Tests: `pytest`.

| route | what |
|---|---|
| `GET /metrics` | the catalog: each metric, its needs, its scalars with direction, placement and unit |
| `POST /measure {store, book, kind, run, pages?, only?}` | records, one per applicable metric |
| `POST /pairs {store, book, kind, run, index}` | the contour metric's verdicts on one page |
| `POST /probe {store, book, kind, run, only?}` | every metric's probes on a run: what fell and what did not |

Adding a metric: a module with a `Metric` subclass declaring `name`, `needs`
and `scalars`, a `probes/<name>.py` beside it, and a line in `METRICS`.
