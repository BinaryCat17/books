# booksmith

Scans of technical books into HTML, in two levels: layout detection on the
CPU, then reading of each block by a vision-language model on a rented card.

This file is the map. The architecture, the rules and the formats are in
`docs/`; the measurements are in the generated `METRICS.md`; how the tree
got this way is in the commit log and nowhere else. A number that has
a record is in `METRICS.md`; a verdict without a record says so.

## Where each kind of text lives

| you want | read |
|---|---|
| the two levels, the three layers, the book directory, the page format, where this is going | `docs/architecture.md` |
| the rules that are not negotiable, and the symbol that enforces each | `docs/rules.md` |
| how to add a detector, a reader, a transport, a metric, a bench | `docs/extending.md` |
| what a model is and the verdict on it | `docs/models.md` |
| every command with its flags | `docs/commands.md` (generated) |
| every knob with its default | `docs/knobs.md` (generated) |
| every metric and what it needs | `docs/metrics.md` (generated) |
| the same as data, for a client that renders metrics it was not told about | `docs/metrics.json` (generated) |
| every measured number | `METRICS.md` (generated) |
| why something is the way it is | `git log`, the commit that made it |

## Code

```
src/booksmith/
  core/        the kernel, imports nothing above itself: page.py (the on-disk
               format), book.py (the book directory and its shape), knobs.py
               (the registry), layers.py (the layer table), stamp.py (hash,
               commit, packages), replay.py (is a snapshot complete), raster.py
               (rendering and crops), policy.py (label to role), order.py
               (assembly order), otsl.py (table markup), textnorm.py, config.py,
               errors.py, job.py (a run's settings, stop and sink), log.py
  processing/  one book, stage by stage: extract/ (djvu to PDF), layout/ (level
               one: detect.py, base.py the Detector contract, adapters/,
               rented/), read/ (level two: driver.py, readers/, transports/,
               rented/), assemble/ (html.py, swap.py, apply.py), assess/ (ink.py)
  datasets/    many books, truth, numbers: bench.py, metrics/ (one module per
               metric and probes/ beside them, one module of probes each),
               make/ (synth/, annopage.py, subset.py), look.py, table.py,
               report.py, docsgen.py
  remote/      renting and running any job on a rented machine; knows nothing
               about books
  cli.py       books <command>
tests/         pytest: unit/ behaviour, contract/ the declarations (layers,
               book shape, formats, knobs, docs, data), bench/ what needs the
               drawn bench, e2e/ what runs a command end to end
tools/         sweep.py: every model over every bench
```

The layer rule: `core` imports nothing; `remote` imports `core`; `processing`
imports `core` and `remote`; `datasets` imports `core` and `processing`; nothing
imports `cli`. Declared in `src/booksmith/core/layers.py` and enforced by
`tests/contract/test_layers.py`.

## The five commands that matter

```
books doctor                 check everything before money moves
books detect <book|pdf>      level one, locally and free
books read <detect dir>      level two, paid
books html <dir>             the book as HTML
books bench all <bench>      every applicable metric, one table, one JSON
```

All of them, with their flags: `docs/commands.md`.

## Knobs

Every knob is declared in `src/booksmith/core/knobs.py`. Reading the
environment past the registry makes a run silently unrepeatable. The list:
`docs/knobs.md`.

## The rules, by name

Nobody repairs the model. What was recognised is untouchable. A metric must
be able to fail. Log the quantity, not the word done. Zero from a check and
zero from not understanding are different zeros. A knob is declared in the
registry. Numbers may be flagged, never restored. One run per label, and a
different identity refuses. Imports go one way. The same book, by hash. Each
with the symbol that enforces it: `docs/rules.md`.

## Tests

```
pytest            the suite
pytest -m slow    the one check that raises an ONNX session
```

Checks that need the drawn bench get it from the `slovar` fixture, which builds
one into a temporary directory once per session. Checks that need detect pages,
a built book or model weights skip with a reason. Whether a metric's numbers can
fall is one case per probe: `books bench selfcheck <book>` asks the same probes
of any bench on disk.

## How this tree is kept

No diaries, no history, no measurements in prose. A document describes the
tree as it is. The commit message describes how it got that way, and it is
long on purpose: what was deleted, and where its surviving facts went. A
measurement lives in `results/` and is rendered into `METRICS.md` by
`books bench report`. A path cited in a document must exist, a generated
document must be current, and prose documents carry no measurement;
`tests/contract/test_docs.py` holds all three.
