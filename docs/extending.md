# Extending

One checklist per kind of thing. Each ends with the command that proves it.

## A layout detector

Served, which is how a model reaches the web and, later, the fleet:

1. An endpoint answering the three routes of `src/booksmith/core/served.py`:
   describe, health, layout. The describe names the model, carries its
   fingerprint with `sha256_weights`, the values of every knob its adapter
   read, and every label it can name mapped onto one of the classes in
   `src/booksmith/core/policy.py`. A hybrid fills content and kind too and
   declares its kinds.
2. An entry in the admin's `models.json`: kind, endpoint, knobs.
3. Prove it: `books detect bench/slovar --model <entry>`, then
   `books bench all bench/slovar --run <label>`; the stand-in
   `tests/fake_layout.py` shows the shape of every answer, and
   `books serve layout` puts any detector of the tree's own behind it.

In process, for a model the tree holds itself:

1. A module under `src/booksmith/processing/layout/adapters/` with a class
   that subclasses `Detector` from `src/booksmith/processing/layout/base.py`
   and implements its abstract members: `label` (the model's own name, a
   directory name), `fingerprint`, `knobs_read`, `read`, `threshold_drift`.
2. Its label vocabulary, whole, as a mapping onto the classes in
   `src/booksmith/core/policy.py`, under `VOCABULARIES`; `Policy.check`
   refuses a vocabulary that is not covered exactly.
3. Its name in `ADAPTERS` and in `_adapter` of
   `src/booksmith/processing/layout/detect.py`.
4. Every knob it reads, declared in `src/booksmith/core/knobs.py` and named
   by `knobs_read`.
5. Page `meta["reading_order"]` is written through `order.declare` in
   `src/booksmith/core/order.py`: the model's rank, ours by a named rule,
   or none.
6. Prove it: `books doctor`, then `books detect bench/slovar` and
   `books bench all bench/slovar --run <label>`.

## A reader

1. A module under `src/booksmith/processing/read/readers/` implementing
   `Reader` from `src/booksmith/processing/read/__init__.py`: `label`,
   `fingerprint`, `knobs_read`, `routes` (class to prompt and kind),
   `pixels`, `cover`.
2. Its name in `READERS` and `build_reader` of
   `src/booksmith/processing/read/driver.py`.
3. An image under `infra/models/<name>/` that raises it behind
   `books serve vlm`, or a shim of its own answering describe and health
   beside its chat route, with a pinned dependency tree as
   `infra/models/paddleocr-vl/Dockerfile` has.
4. Prove it: `books crop` on a detect run, then `books read` against
   `tests/fake_vlm.py` through the test suite before any money moves.

## A transport

1. A module under `src/booksmith/processing/read/transports/` implementing
   `Transport`: `fingerprint`, `knobs_read`, `check`, `send`.
2. `send` returns a `Said` always; a delivery failure is a value in
   `Said.error`, not an exception. An answer with status 200 is never
   repeated.
3. Prove it: the read tests against the fake server.

## A metric

1. A module under `src/booksmith/datasets/metrics/` with a class that
   subclasses `Metric` from `src/booksmith/datasets/metrics/base.py`: `name`,
   `needs` (a subset of `truth`, `pages`, `pdf`, `content`, `read`), `run` or
   `run_loaded`, returning a `Record` of `Scalar`s.
2. A null scalar carries a reason; a share carries its count and is the
   count's quotient; a coverage carries its unit; a value per page or per
   block is keyed by anchor, with the side whose blocks it names.
3. A `probes/<name>.py` module beside it, exposing `probes(bench, run)`: the
   probes that spoil the input and demand the number fall, using the spoilers
   in `src/booksmith/datasets/metrics/mutate.py`. Each probe names what was
   spoiled and what must happen to the number, returns True, False, or None
   where this book gives it nothing to grip.
4. Every scalar declared in the class's `scalars` as a `Spec`: its name,
   which way is better, one sentence of what it says, and the report
   question it headlines if any. The report and `docs/metrics.md` derive
   from that; an undeclared scalar is refused.
5. An instance in `METRICS` of `src/booksmith/datasets/metrics/__init__.py`.
6. Prove it: `books bench all bench/slovar`, then `books bench selfcheck
   bench/slovar`, then `books bench report` and `books docs`, then `pytest`.

## A bench

1. A directory under `bench/` with `manifest.json` carrying `book` and
   `source: {name, sha256}`, and the scan beside it.
2. `truth/NNNN.json`, one per page, in the page format of
   `src/booksmith/core/page.py`, with `width` and `height` in the raster the
   runs will be compared to.
3. Per page, `meta.text_marked` and `meta.order_marked` set honestly; a
   missing flag reads as "not said". Table truth under
   `meta.artifact_truth[block_id]` as rows, cols and cells. Objects the
   vocabulary cannot express under `meta.out_of_scope`.
4. A builder writes to `truth.new/` and renames, so an interrupted build
   leaves no half-bench.
5. Prove it: `books detect bench/<name>` and `books bench all bench/<name>`.
