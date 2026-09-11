# backend

The books service: users and sessions, a store per user, jobs in the
background, the pipeline (layout through a served model, reading through a
served VLM, the document and its exports, corrections as derived runs),
the viewer's data, and the catalog of runs and measurements.

Run: `python -m backend`. Environment: `BOOKSMITH_HOME` (the data volume),
`BOOKSMITH_SCHEMA` (the schema directory), `BOOKSMITH_METRICS` (the metrics
service), `BOOKSMITH_FLEET` (the model manager) and `FLEET_KEY` (its key), `BOOKSMITH_WORKERS`, `BOOKSMITH_SECURE_COOKIES`, `BOOKSMITH_COMMIT`,
`PORT`, `BOOKSMITH_ADMIN=name:password` (the first admin, made when there
are no users). Model keys come from the registry entry's `api_key`. Tests: `pytest`.

The API is under `/api`; its OpenAPI document is served at `/api/openapi.json`.
Book routes take `{root}/{name}`, `bench/<name>` or `processed/<name>`.

Truth: a book's own `truth/`, or borrowed from the bench in the admin's
store whose scan has the same sha256 (two such benches refuse). A run says
which (`own`, `borrowed`, none); users get the run side of a comparison
only. A layer is `truth.layers/NNNN-<when>-<author>.json`, a whole page in
the base page's raster, written once (`when` is UTC to the microsecond);
the newest layer of a page is its truth, the base files are never
rewritten. A measurement records the truth's fingerprint and reads `stale`
once a layer lands.

| route | what |
|---|---|
| `POST /login`, `POST /logout`, `GET /me` | sessions, two roles |
| `GET /books`, `POST /books`, `DELETE /books/{root}/{name}` | a user's library |
| `GET /books/{root}/{name}/runs` | the runs of a book |
| `GET /books/{root}/{name}/runs/{kind}/{label}` | one run: identity, policy, pages |
| `GET /books/{root}/{name}/pages/{index}/image` | the scan's page as PNG |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}` | one page of the document |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}/pairs` | the contour metric's verdicts; the truth side for admins |
| `POST /books/{root}/{name}/truth {kind, label}` | a blank truth for a book in the raster of that run, one page per page of the scan (admin) |
| `GET\|PUT /books/{root}/{name}/truth/pages/{index}` | the effective truth page; a PUT writes a layer (admin) |
| `GET /classes` | the class table |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}/metrics` | every metric on one page, measured now |
| `GET /books/{root}/{name}/runs/{kind}/{label}/crops/{anchor}` | one block as PNG |
| `GET /books/{root}/{name}/runs/{kind}/{label}/document` | the book as data |
| `GET /books/{root}/{name}/runs/{kind}/{label}/export/{html\|markdown\|text}?math=cdn\|off` | the document rendered, one file, crops inside |
| `GET\|POST /books/{root}/{name}/runs/{kind}/{label}/corrections`, `DELETE …/corrections/{n}` | the corrections of a run, kept in `<label>.corrected` beside it |
| `GET /books/{root}/{name}/runs/{kind}/{label}/results` | the last measurement of the run |
| `GET /books/{root}/{name}/runs/{kind}/{label}/series` | every measurement of the run |
| `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events` | detect, hybrid, read, bench; progress as events |
| `GET /models`, `PUT /models`, `GET /models/presets`, `GET /users`, `POST /users` | the registry (kept by the fleet) and the users (admin) |
| `GET /fleet/placements`, `DELETE /fleet/placements/{id}`, `GET /fleet/ledger` | what the fleet runs and what it cost (admin) |

Corrections: `{anchor, content | label | drop}` on a run or on its derived
run; each one rewrites `<kind>/<label>.corrected/` from the base run (pages
with the corrections applied, the base's answers minus the corrected
blocks, its crops linked), with `derived_from` and `corrections` in
`run.json` and an identity of its own. The base run is never written.
