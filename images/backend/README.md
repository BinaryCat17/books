# backend

The books service: users and sessions, a store per user, jobs in the
background, the pipeline (layout through a served model, reading through a
served VLM, the document, the HTML export), the viewer's data, and the
catalog of runs and measurements.

Run: `python -m backend` with `BOOKSMITH_HOME` (the data volume),
`BOOKSMITH_SCHEMA` (the schema directory), `BOOKSMITH_METRICS` (the metrics
service). Tests: `pytest`.

API under `/api`; the OpenAPI document is served at `/api/openapi.json`.

| route | what |
|---|---|
| `POST /login`, `POST /logout`, `GET /me` | sessions, two roles |
| `GET|POST /books`, `DELETE /books/{root}/{name}` | a user's library |
| `GET /books/{root}/{name}/runs`, `.../runs/{kind}/{label}` | the runs of a book |
| `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events` | detect, hybrid, read, html, bench; progress as events |
| `.../pages/{index}/image`, `.../runs/{kind}/{label}/pages/{index}`, `.../crops/{anchor}` | the page, its image, a crop |
| `.../runs/{kind}/{label}/pages/{index}/pairs`, `.../metrics` | the metrics' verdicts and numbers for one page |
| `.../runs/{kind}/{label}/document` | the book as data |
| `.../runs/{kind}/{label}/results`, `.../series` | the measurements of a run, last and all |
| `GET|PUT /models`, `GET /models/presets`, `GET|POST /users` | the registry and the users (admin) |
