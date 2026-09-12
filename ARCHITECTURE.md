# booksmith

Scans of technical books become a document: a layout model draws the boxes,
a vision-language model reads each box, and one rule assembles the document
every export renders. Every run is measured against truth where truth
exists. Users keep libraries of books; admins keep the models, the truth
and the labels.

## Systems

One directory per image under `images/`, each self-contained: its own
package, tests, `pyproject` and `Dockerfile`. Nothing is imported across
them. `schema/` is the only thing shared, and it is data.

| directory | what it is | runs as |
|---|---|---|
| `schema/` | the contracts: JSON Schema for every payload, OpenAPI for every API, the class table | data |
| `images/backend` | users, libraries, jobs, the pipeline, the document, the viewer, the catalog | container |
| `images/metrics` | every metric with its declaration and probes; catalog, measure, pairs, probe | container |
| `images/fleet` | the model manager: registry, providers, placements, leases | container |
| `images/layout` | a layout detector behind the model protocol, one tag per model | container per model |
| `images/vlm` | a vLLM behind the model protocol | container |
| `images/datasets` | the bench builders | tool container |
| `images/ui` | the browser application: library, viewer, admin; built into the proxy image | static |
| `infra/` | the compose file | — |

## Contracts

**Schemas.** `page` (a model's boxes, or truth), `document` (the book as
data), `describe`, `health`, `layout-request` (the model protocol),
`snapshot` (`run.json`), `record` and `catalog` (what a metric says and
publishes), `classes.json` (the class table and the vocabularies that map
onto it). The backend, metrics, layout, vlm and datasets images validate what they
read and write against them in their tests; the backend's API is
`openapi/backend.json`, held to the code by a test, and the UI's client is
its hand-typed reading. JSON over HTTP throughout.

**Model protocol.** `GET /booksmith/describe`, `GET /booksmith/health`,
`POST /booksmith/layout` for layout and hybrid models; the OpenAI chat route
for readers. The describe carries kind, label, fingerprint, the mapping of
the model's labels onto the class table, the knob values its side read, and
the commit serving. A model container reads `BOOKSMITH_PORT`,
`BOOKSMITH_SERVE_KEY` and `BOOKSMITH_IDLE_S` from its environment. A run's
identity is the hash of the fingerprint and both sides' knob values: what the
model serves, never where it runs.

**Fleet API.** `GET|PUT /models`: the registry, `{name: {kind, endpoint |
image + provider, knobs, api_key, env, gpu, gpu_name, port, idle_s,
budget_usd, max_dph, disk_gb, min_reliability, min_down_mbps, cuda_min}}`.
`POST /leases {model, job, wait_s}` answers an endpoint, a key and a lease,
or `starting` when the placement is not ready in time; `POST /leases/renew
{job}` and `POST /leases/release {job}` are a job's hold on it.
`GET /placements`, `DELETE /placements/{id}`, `POST /reconcile`,
`POST /sweep`, `GET /ledger`; all behind `FLEET_KEY`. Providers: `docker` on
the fleet's daemon, `vast` on a rented card with the port published, plain
HTTP over the internet with the placement's key. A placement with no live
lease past `idle_s` is stopped; one past its budget, a bound per placement,
is destroyed whatever is running; one that died is dropped; one the table
does not know is destroyed at reconcile. A model container exits on its own
after `BOOKSMITH_IDLE_S` without a request, and on vast destroys its
instance. The backend never knows where a model runs: it names the model,
holds the lease while its job runs, and releases it after.

**Metrics API.** `GET /metrics`: the catalog. `POST /measure {store, book,
kind, run, truth?, pages?, only?}`: records. `POST /pairs {…, index}`: the
contour metric's verdicts on one page. `POST /probe`: what falls and what
does not. `truth` names a bench's truth of the same scan for a book with none.
Stateless; reads the storage volume.

**The document.** Assembled from a run's pages by one rule: blocks in reading
order with their role by the run's policy, their content by kind, what nests
and repeats, what the reading flagged. Written as `document.json` beside the
run, regenerated when the rule's version or the run's identity changes.
Exports (`html`, `markdown`, `text`) render it and nothing else, on
request, as one file; the run's pages stay untouched.

**Corrections.** A correction is one block's text, label, or absence,
named by anchor (`correction.schema.json`). Corrections never touch the run
they fix: they live in the snapshot of a derived run beside it,
`<label>.corrected`, whose pages are the base's with the corrections
applied, whose identity is the base's identity and the corrections, and
which is measured, documented and exported like any run.

**Storage.** One volume, one layout, mounted by backend, metrics, fleet and
datasets. A store per owner; the admin's is the root.

```
<store>/booksmith.sqlite     the catalog
<store>/models.json          the fleet's registry
<store>/fleet/               placements.json, ledger.jsonl
<store>/users/<id>/          a user's own store, laid out as below
<store>/raw/                 scans as uploaded, before they are a book
<store>/bench/<name>/        a book with truth
<store>/processed/<name>/    a book without
  manifest.json              {book, source: {name, sha256}}
  <scan>.pdf
  truth/NNNN.json            pages in the page format; never rewritten
  truth.layers/NNNN-<when>-<author>.json   a whole page, written once; the newest is the page's truth
  detect/<label>/            a level-one run: run.json, pages/, document.json
  read/<label>/              a level-two run: run.json, pages/, answers/, crops/, document.json
  <kind>/<label>.corrected/  a derived run: the base's pages under its corrections, run.json naming them
```

**Backend API.** Sessions and two roles. Books: upload, list, delete. Runs of
a book. Jobs: detect, read, hybrid, bench, with progress as events and a cancel.
Pages: the data, the image, a crop, the pairs against truth, the metrics of
one page. The document and its exports. Corrections: list, add, undo,
and re-derive after the base has re-run. Measurements: the last and the series.
Truth: a book's own, or borrowed from the bench whose scan has the same
hash; admins start one and write layers from the browser. Admin: the
registry through the fleet, the users, the fleet's placements and ledger.

**Catalog** (the backend's database): `users`, `sessions`, `jobs`,
`measurements` (run, metric, identity, truth fingerprint, commit, when,
pages, scalars; append-only). Truth, its layers and corrections live in the store, not the
catalog.

## Rules

Six, each guarding a number. Everything else is convention.

1. Nobody repairs the model. What was recognised is untouchable; a correction is a derived run beside it.
2. A metric must be able to fail. Every metric ships probes that spoil its input, and the number must fall on each.
3. A zero from a check and a zero from not understanding are different. A null carries its reason.
4. Identity is what a model serves, never where it runs. One run per label; a different identity refuses.
5. A setting is declared, read through the job, and recorded in the run.
6. A store reaches only itself. Every path a request names resolves inside the caller's store.

## Documentation

This file is the map. Each image has one `README.md`: what it is, how to run
it, its API. A commit message is one line, with a paragraph when the why is
not obvious. No generated documents, no measurements in prose, no history
anywhere but git.

## Order of work

1. The split into `schema/` and `images/`. Done.
2. The fleet: the registry, the docker and vast providers, placements and leases, the backend holding a lease while a job runs. Done; a real rental is proven on demand, since it costs money.
3. The UI: library, viewer with boxes, metrics per page and per book, the admin panel. Done.
4. Truth by hash, truth layers, labeling in the browser. Done.
5. Export beyond HTML, and corrections as derived runs. Done.
