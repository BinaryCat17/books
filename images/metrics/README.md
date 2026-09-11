# metrics

Every metric with its declaration and its probes, behind four routes. The
service is stateless and reads the storage volume.

Run: `python -m metrics` with `BOOKSMITH_HOME` and `BOOKSMITH_SCHEMA`.
Tests: `pytest`.

| route | what |
|---|---|
| `GET /metrics` | the catalog: each metric, its needs, its scalars with direction, placement and unit |
| `POST /measure {store, book, kind, run, truth?, pages?, only?}` | records, one per applicable metric |
| `POST /pairs {store, book, kind, run, truth?, index}` | the contour metric's verdicts on one page |
| `POST /probe {store, book, kind, run, only?}` | every metric's probes on a run: what fell and what did not |

`truth` is `bench/<name>/truth` at the root of the volume, for a book with
no truth of its own; the bench must be about the same scan. A page's truth
is the newest layer in `truth.layers/` beside it, else its base file, and
every record carries `truth_sha256`, the fingerprint of what it was
measured against.

Adding a metric: a module with a `Metric` subclass declaring `name`, `needs`
and `scalars`, a `probes/<name>.py` beside it, and a line in `METRICS`.
