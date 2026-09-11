# backend

The books service: users and sessions, a store per user, jobs in the
background, the pipeline (layout through a served model, reading through a
served VLM, the document, the HTML export), the viewer's data, and the
catalog of runs and measurements.

Run: `python -m backend`. Environment: `BOOKSMITH_HOME` (the data volume),
`BOOKSMITH_SCHEMA` (the schema directory), `BOOKSMITH_METRICS` (the metrics
service), `BOOKSMITH_FLEET` (the model manager), `BOOKSMITH_WORKERS`, `BOOKSMITH_SECURE_COOKIES`, `BOOKSMITH_COMMIT`,
`PORT`. Model keys come from the registry entry's `api_key`. Tests: `pytest`.

The API is under `/api`; its OpenAPI document is served at `/api/openapi.json`.
Book routes take `{root}/{name}`, `bench/<name>` or `processed/<name>`.

| route | what |
|---|---|
| `POST /login`, `POST /logout`, `GET /me` | sessions, two roles |
| `GET /books`, `POST /books`, `DELETE /books/{root}/{name}` | a user's library |
| `GET /books/{root}/{name}/runs` | the runs of a book |
| `GET /books/{root}/{name}/runs/{kind}/{label}` | one run: identity, policy, pages |
| `GET /books/{root}/{name}/pages/{index}/image` | the scan's page as PNG |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}` | one page of the document |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}/pairs` | the contour metric's verdicts; the truth side for admins |
| `GET /books/{root}/{name}/runs/{kind}/{label}/pages/{index}/metrics` | every metric on one page, measured now |
| `GET /books/{root}/{name}/runs/{kind}/{label}/crops/{anchor}` | one block as PNG |
| `GET /books/{root}/{name}/runs/{kind}/{label}/document` | the book as data |
| `GET /books/{root}/{name}/runs/{kind}/{label}/results` | the last measurement of the run |
| `GET /books/{root}/{name}/runs/{kind}/{label}/series` | every measurement of the run |
| `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events` | detect, hybrid, read, html, bench; progress as events |
| `GET /models`, `PUT /models`, `GET /models/presets`, `GET /users`, `POST /users` | the registry (kept by the fleet) and the users (admin) |
