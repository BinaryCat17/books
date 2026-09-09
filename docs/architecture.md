# Architecture

## The two levels

**Level one** walks the whole scan and returns contours: boxes, labels and a
reading order. It is a layout detector, not a recogniser, and it returns not
one character of text. It runs on the CPU with ONNX and costs nothing.

**Level two** takes each block in isolation from its neighbours and turns it
into a fragment of HTML. A vision-language model reads a crop of the block
and answers with text, a table in OTSL markup, or LaTeX. Substitution into
the book goes one block at a time, with a journal and an undo, so any block
can be checked, rolled back and redone by another model without touching the
rest.

The order of work was the reverse of the usual one: benches and instruments
first, models second.

## The data flow

```
raw/<book>.djvu
  books prepare      djvu to PDF, spreads cut apart
<book>.pdf
  books detect       one Page per sheet, blocks with box, label, order
detect/<model>/pages/NNNN.json + run.json
  books crop         what read would send, cut by the same path; nothing sent
  books read         the same pages with content and kind filled in
detect/<model>.read/pages/NNNN.json + answers/pNNNN.json + run.json
                     (written beside the detect run today; read/<model>/ is
                     the mapped home and the two on disk were moved by hand)
  books html         book.html, crops, blocks.json, the swap journal
book.html + assets/
  books apply        markup placed per anchor, journaled, undoable
```

A bench is a book that also carries `truth/`, in the same page format.
`books bench all` writes one JSON of records per bench and run into
`results/`, and `books bench report` renders every record into `METRICS.md`.

## The three layers

Imports go one way. The table is the whole rule; `tests/test_imports.py`
walks every import in the package against it.

| package | may import |
|---|---|
| `core` | nothing |
| `remote` | `core` |
| `tree` | `core` |
| `processing` | `core`, `remote` |
| `datasets` | `core`, `processing` |
| `cli` | anything; nothing imports `cli` |

`core` is the kernel: the on-disk format, the book directory, the knob
registry, the snapshot, rendering, the label policy, the assembly order, the
table markup parser, errors. `processing` is one book, stage by stage.
`datasets` is many books, truth and numbers. `remote` rents a machine and
runs any job on it; it knows nothing about books, so the next task on a
rented card does not mean rewriting the renting.

## The book directory

One directory per book, one directory per run. A bench is a book with
`truth/`. `src/booksmith/tree/layout.py` declares this shape and
`tools/layout.py` walks `bench/` and `processed/` against it.

```
bench/<book>/ or processed/<book>/
  manifest.json        source: {name, sha256}: which scan this is about
  <source>.pdf         the scan, under the name the manifest gives
  truth/               only a bench has this; pages in the page format
  detect/<model>/      a level-one run: pages/ and run.json
  read/<model>/        a level-two run: pages/, answers/, crops/, run.json
  look/<model>.pdf     boxes drawn over the pages, for the eye
  look/truth.pdf       truth drawn with no model beside it
  book.html            the built book, one file, referring to nothing outside
  assets/              its kitchen: blocks/*.png, blocks.json, run.json,
                       swaps.json, source/ (what the book was built from)
```

The label of a run is the model's own name, asked of the adapter, never the
adapter's name: one adapter serves several models, and two runs under one
directory would read as one run resumed. `run.json` carries `identity`, a
hash over the fingerprint and the values of the knobs the run read.
`books detect` refuses to write a different identity under an existing
label, a partial run over a whole one, or a run it cannot compare.

The built book is self-sufficient except for the scan: MathJax and the crops
are inlined, and `assets/source/` holds the pages and answers it was built
from, so `books apply` rebuilds from there on any machine.

## The page format

One shape for truth, detection and reading, so one metric can compare any
two of them. Declared in `src/booksmith/core/page.py`.

| field | meaning |
|---|---|
| `Page.index`, `width`, `height`, `dpi` | the sheet, in pixels at that dpi |
| `Page.blocks` | the blocks, in the order the model returned them |
| `Page.raw` | the model's answer before parsing, kept apart from what we parsed |
| `Page.meta` | circumstances of the run; `reading_order` says whose order the blocks carry |
| `Block.block_id` | restarts on every page |
| `Block.box` | `(x0, y0, x1, y1)` in page pixels, origin top left |
| `Block.label` | in the model's own vocabulary; the role comes from the policy |
| `Block.score` | the model's, or null |
| `Block.order` | the model's rank, or null where it gave none; ties travel on |
| `Block.content`, `kind` | filled by level two; kind is one of `html`, `otsl`, `latex`, `text`, or `none` |
| `Block.source_category` | truth only: the category the annotators marked |

A block is addressed by its anchor, `p<index>-b<block_id>` with the index
zero-padded to four digits, in the answers, the journal and the book.

Truth carries what it knows and says what it does not: `meta.text_marked`
and `meta.order_marked` are three-state, and a missing flag means "not
said", never "yes". Table truth is `meta.artifact_truth[block_id]` as rows,
columns and cells; OTSL is what the model returns, not what truth stores.
Objects the annotators saw but the vocabulary cannot express stay in
`meta.out_of_scope`, so a box the model puts there is not counted against it.

## Measuring

A metric declares what it `needs` from the pair of bench and run: `truth`,
`pages`, `pdf`, `content` (the truth carries characters), `read` (the run
does). It runs only where its needs are met, and the table says why it did
not otherwise. It returns a record of scalars. A scalar carries its value,
the count behind a share, the coverage it was measured over with its unit,
and, when the value is null, the reason. A null without a reason cannot be
constructed.

Every metric has a battery of deliberately spoiled input, and the number
must fall on each probe before the metric is believed. Which metrics exist
and what each needs: `docs/metrics.md`. Every number: `METRICS.md`.

The benches, and how each is rebuilt:

| bench | truth | rebuilt by |
|---|---|---|
| `slovar`, `spravochnik`, `matematika`, `atlas`, `katalog`, `zhurnal` | drawn, exact: characters, grids, ink | `books synth --book <name>`, byte for byte |
| `annopage` | real pages, objects by librarians, no text | `books annopage raw/annopage` |
| `hard` | the distillate of annopage: same-label neighbours side by side | `books subset` |
| `annopage-lite`, `hard36` | the same truth, squeezed | nothing: built by a script that no longer exists |
| `real-*` | none: books, not benches | they are the source |

## What cannot be measured yet

The golden bench annotates no text, so the reading of level two can only be
measured on the drawn benches. The drawn benches are rendered at a lower
resolution than the real scans, and their pages are typeset with a font, not
printed by letterpress and aged. So the number a paid run returns is a lower
bound and a proof that the pipe works, not a prediction of quality. A bench
of real scans with known text does not exist; the three `real-*` books are
its raw material.

## Where this is going

The next layer is a web application: a collection of uploaded books, both
levels run as jobs with progress, metrics per page and per book that appear
in the interface when a metric is added, truth uploaded or drawn in the
browser, corrections journaled, page images with the boxes over them. The
library is the engine of that application; the seams it needs are these, and
each is a refactor of what exists:

- Metric metadata on the metric itself: direction, gloss, kind per scalar,
  so a new metric renders without a hand-kept table.
- Per-page results kept by the ink measurement and returned as data by the
  overlay, instead of book totals and a drawn PDF.
- Progress as data from `detect.run` and `read_book`, not lines of text.
- The HTML builder split into the data pass and the emission, so the data
  pass serves a page viewer and the emission becomes an export.
- A bytes-returning render and crop in `core/raster.py`.
- A collection enumerator, `Book.list(root)`.
- A knob source that is not the process environment, so one server can run
  jobs with different settings.

Two decisions are already made. A correction of what the model returned is
never a write into the model's run; it is a derived run beside it, journaled
with its trigger, and the bench measures the raw run unless told otherwise.
An edit to truth is an append-only layer beside `truth/`, with author and
time, never an edit in place.

## Glossary

| word | meaning |
|---|---|
| anchor | the address of a block, `p<index>-b<block_id>` |
| artifact | a block cut out as a picture and taken apart by level two: table, figure, formula |
| bench | a book directory that also has `truth/` |
| book | a directory with `manifest.json` naming a scan |
| contour | a box with a label and an order, and no text |
| derived run | a run made from another by correction; `run.json` names its source |
| furniture | running heads, folios, footnotes: marked and kept, not read |
| identity | the hash in `run.json` over the fingerprint and the knobs the run read |
| label | the model's own name for a block, or the model's own name for a run |
| level one, level two | detection, reading |
| policy | the table from a model's labels to the three roles: text, artifact, furniture |
| role | text stays in the flow, an artifact becomes a picture, furniture is marked |
| run | one model over one book, under one label, with its snapshot |
| trait | a fact truth declares about itself per page: text marked, order marked; three-state |
