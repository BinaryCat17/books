# booksmith

Scans of technical books become HTML in two levels: a layout model draws the
boxes, a vision-language model reads each box. Every run is measured against
truth where truth exists. Users keep libraries of books; admins keep the
models, the truth and the labels.

## Systems

One directory per system. Each is a package with its own `pyproject`, its
own tests and, where it runs, its own image. `formats` is the only shared
code. Nothing is nested deeper than one level.

| directory  | what it is | runs as | depends on |
|------------|------------|---------|------------|
| `formats`  | the page format, anchors, the class table, the model protocol, identity | library | — |
| `models`   | one container per model, answering the model protocol | container per model | formats |
| `fleet`    | the model manager: registry, providers, placements, leases, ledger | container | formats, providers |
| `backend`  | books: users, libraries, jobs, the pipeline, the viewer, truth, the catalog | container | formats, fleet, models, metrics, storage |
| `metrics`  | every metric with its declaration and probes; a catalog and a measure endpoint | container | formats, storage |
| `datasets` | bench builders: drawn benches, AnnoPage, subsets | tool container | formats, storage |
| `ui`       | the browser application | static, behind the proxy | backend API |
| `infra`    | compose, images, CI | — | — |

## Contracts

**Model protocol** (`formats`). A model answers `GET /booksmith/describe`,
`GET /booksmith/health` and, for layout and hybrid models,
`POST /booksmith/layout`; a reader answers the OpenAI chat route. The
describe carries kind, label, fingerprint, the mapping of the model's
labels onto the class table, the knob values its own side read, the kinds it
returns, and the commit of the code serving. A run's identity is the hash of
the fingerprint and both sides' knob values: what the model serves, never
where it runs.

**Fleet API.** `GET|PUT /models`: the registry, `{name: {kind, endpoint |
image + provider, knobs, key, idle_s, budget}}`. `POST /leases {model, job}`
answers an endpoint and a lease, bringing a placement up if none is ready.
`POST /leases/{id}/renew`, `DELETE /leases/{id}`. `GET /placements`,
`GET /ledger`. A placement with no live lease past `idle_s` is stopped; a
placement the table does not know is destroyed; a placement past its budget
is destroyed whatever is running.

**Metrics API.** `GET /metrics`: the catalog, each metric with its needs and
its scalars, each scalar with its direction, where its values sit (page or
block, of which side) and the unit of its coverage. `POST /measure {book,
kind, run, pages?, only?}` answers records: one per metric, each scalar with
its value, its count, its coverage, its reason when null, and its values per
anchor. `POST /probe` runs every metric's probes on a run and answers what
fell and what did not. The service is stateless and reads the storage volume.

**Storage.** One volume, one layout, mounted by backend, metrics and datasets.
A store per owner; the admin's is the root.

```
<store>/bench/<name>/        a book with truth
<store>/processed/<name>/    a book without
  manifest.json              {book, source: {name, sha256}}
  <scan>.pdf
  truth/NNNN.json            pages in the page format, plus truth layers
  detect/<label>/            a level-one run: run.json, pages/
  read/<label>/              a level-two run: run.json, pages/, answers/, crops/
  look/                      overlays
```

**Backend API.** Sessions and two roles. Books: upload, list, delete. Runs of
a book. Jobs: detect, read, hybrid, html, bench, with progress as events and
a cancel. Pages: the data, the image, a crop, the pairs against truth, the
metrics of one page. Measurements: the series of a run. Truth: layers, and
labeling for admins. Admin: the registry through the fleet, users.

**Catalog** (the backend's database). `users`, `sessions`, `jobs` as today,
and the links that make a book more than a directory:

```
books         store, path, sha256
runs          book, kind, label, identity, source_sha256, when
truths        sha256 -> bench path; a user's book with a bench's hash borrows its truth
measurements  run, metric, identity, commit, when, pages, scalars   (append-only)
labels        truth layer, author, when                              (later)
corrections   run, derived run, trigger, when                        (later)
```

## Rules

Six, each guarding a number. Everything else is convention.

1. Nobody repairs the model. What was recognised is untouchable; a correction is a derived run beside it, never a write into it.
2. A metric must be able to fail. Every metric ships probes that spoil its input, and the number must fall on each.
3. A zero from a check and a zero from not understanding are different. A null carries its reason; nothing prints a zero it did not count.
4. Identity is what a model serves, never where it runs. One run per label; a different identity refuses.
5. A setting is declared, read through the job, and recorded in the run. A snapshot says what it read; the knob registry says what exists.
6. A store reaches only itself. Every path a request names resolves inside the caller's store, outputs included.

## Removed

The command line, whole: a container has a command and a developer uses
compose. `METRICS.md`, the report, the sweep, the results files: a
measurement is a row in the catalog. The generated documents and the tests
that guarded them. The rules document with its cited symbols. `service.py`
and `cli.py`, dissolved into the backend.

## Documentation

This file is the map. Each system has one `README.md`: what it is, how to
run it, its API. A commit message is one line, with a paragraph when the why
is not obvious. No generated documents, no measurements in prose, no
history anywhere but git.

## Order of work

1. The split: the flat tree, `formats` extracted, each system its package with its tests beside it, compose for the whole; the removals above. No behaviour changes.
2. The catalog and the metrics service: measurements as a series in the backend's database, metrics behind their two endpoints.
3. The fleet: the registry, the docker and vast providers, placements and leases, the backend renewing a lease while a job runs.
4. The UI: library, viewer with boxes, metrics per page and per book, the admin panel.
5. Truth by hash, truth layers, labeling in the browser.
6. Export, and corrections as derived runs.
