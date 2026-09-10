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

## The data flow

```
raw/<book>.djvu
  books prepare      djvu to PDF, spreads cut apart
<book>.pdf
  books detect       one Page per sheet, blocks with box, label, order
detect/<model>/pages/NNNN.json + run.json
  books hybrid       boxes and content in one call from a served hybrid
                     model, filed as read/<model>/ with no detect run behind it
  books crop         what read would send, cut by the same path; nothing sent
  books read         the same pages with content and kind filled in
detect/<model>.read/pages/NNNN.json + answers/pNNNN.json + run.json
                     (beside the detect run unless --out names read/<model>/,
                     the book directory's home for it)
  books html         book.html, crops, blocks.json, the swap journal
book.html + assets/
  books apply        markup placed per anchor, journaled, undoable
```

`books bench all` writes one JSON of records per bench and run into
`results/`, and `books bench report` renders every record into `METRICS.md`.

## The layers

Imports go one way. The table is the whole rule, declared in
`src/booksmith/core/layers.py`; `tests/contract/test_layers.py` walks every
import in the package against it.

| package | may import |
|---|---|
| `core` | nothing |
| `remote` | `core` |
| `processing` | `core`, `remote` |
| `datasets` | `core`, `processing` |
| `serving` | `core`, `processing` |
| `service` | `core`, `remote`, `processing`, `datasets` |
| `web` | `core`, `remote`, `processing`, `datasets`, `service` |
| `cli` | all of them; nothing imports `cli` |

`core` is the kernel: the formats, the registries and the rules the rest
obey. `processing` is one book, stage by stage. `serving` is the model side
of the protocol: a detector or a vLLM of the tree's own behind HTTP.
`datasets` is many books, truth and numbers. `remote` rents a machine and
runs any job on it; it knows nothing about books, so the next task on a
rented card does not mean rewriting the renting. `service` is what the CLI
and the web share: one function per command, each taking a store and the
run's settings. `web` is users, their stores, jobs in the background and
HTTP over the service.

## The model protocol

A model is something that answers three routes, declared in
`src/booksmith/core/served.py`. `GET /booksmith/describe` says what it is:
its own name, its fingerprint, the values of the knobs its own adapter read,
its labels mapped onto the tree's classes and, for a reader, the name its
chat route answers to.
`GET /booksmith/health` says whether it is ready and when it last worked.
`POST /booksmith/layout` takes one page as a data URI and returns one page
in the page format; a hybrid fills `content` and `kind` too. A reader keeps
the OpenAI chat route at `/v1` beside them, and so may a hybrid, which level
two then reads through; a bare vLLM with no describe is still accepted
through `/models`.

`LAYOUT_ADAPTER=served` reaches a layout or hybrid model at
`LAYOUT_ENDPOINT` through
`src/booksmith/processing/layout/adapters/served.py`, which asks describe
once, posts each page, and refuses an answer that is not a page, a page at
another dpi or size than the raster sent, a label the model did not declare,
or text from a model that declared none. A layout answer is never asked
twice. Identity is what a model serves, never where it
runs: the run's identity hashes the describe's fingerprint with the knobs the
server read and the knobs this process read, and the address and the adapter
that reached it stay out, so a served run of a model and an in-process run
of it under one setting are one experiment. The snapshot carries the
describe whole under `served`, and `books replay --check` takes its code
hash and commit for the adapter's source.

The tree declares its classes in `src/booksmith/core/policy.py`, each with
its role, text, artifact or furniture, and the name the order rules read. A
model maps every label it can name onto one of them, whole; the five
vocabularies of the tree's own adapters are five such mappings; the reader
routes its prompts by class; a run's snapshot carries the mapping under
`policy`, and every measurement, the built book and the reading take a
block's role from the run's own mapping, never from a table this process
happens to know. A describe that names one of the tree's vocabularies must
map as the tree does, and then a served run shares the in-process run's
identity; a mapping of the model's own is in its identity, since the roles
decide the book and the numbers. Truth carries no mapping of its own yet
and is read under the union of the five.

The tree serves its own models. `books serve layout` puts the detector
`LAYOUT_ADAPTER` names behind the three routes, `books serve vlm` raises a
vLLM and puts describe and health beside its chat route, which passes
through byte for byte; both are in `src/booksmith/serving/`. `infra/models/`
holds one image per model with its weights baked in, one Dockerfile for the
six detectors and one for PaddleOCR-VL, built and pushed by
`.github/workflows/models.yml`; a start is a pull, not a provisioning. A
served run of a model of the tree's own carries the identity of the
in-process run under the same settings, which `tests/unit/test_serving.py`
holds it to.

A hybrid model returns boxes and text in one call. `books hybrid` files its
pages as a read run with its own boxes, `read/<model>/` with `layout: own`
in `run.json` and no detect run behind it; the metrics apply by what the
pages carry, as they do to any run. `tests/fake_layout.py` answers the three
routes from a truth directory, so all of this is checked with no weights.

## The book directory

One directory per book, one directory per run. A bench is a book with
`truth/`. The shape is declared in `src/booksmith/core/book.py` and
`tests/contract/test_book_shape.py` walks the tree against it. A store is a
directory holding `bench/` and `processed/` in this shape, with its own
`results/` and `raw/`. There are two roots, declared in
`src/booksmith/core/config.py`: the install path, which is the repository,
the source of the generated documents and the commit, and the data home,
`BOOKSMITH_HOME`, which is the admin's store and falls back to the install
path when unset, so a developer's tree is its own data home. A user's store
is `users/<id>/` under the data home, and a book's owner is the store it
lies in; a book under neither `bench/` nor `processed/` is the admin's. A
store other than the admin's reaches only its own paths, outputs included,
by their real paths, and runs only a preset from the admin's `models.json`,
or the registry's defaults. An entry of that registry
names a model: its kind, layout, reader or hybrid; its knobs, the values a
preset runs with; and either the endpoint it answers at or the image and
provider that will bring one up. A key for the endpoint rides in the entry
and reaches the job as a secret, never a snapshot.

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

## The web

`books web serve` runs the backend, `src/booksmith/web/`: users with hashed
passwords and cookie sessions, two roles, one sqlite file in the data home
for users, sessions and jobs, and routes that take names, never paths. A
job is a row and a thread over one job context of its own, whose settings
are the registry entry's, whose secrets are the entry's key, whose stop is
the row's cancel and whose sink turns the log's counts into progress on the
row and into events a client listens to. Every long loop says where it is
and asks for the stop between pages and between metrics. The run directory
stays the record of the result; a row left running or queued by a dead
process is failed at the next boot, never resumed blind. `books web user` makes a
user and their store. What the web does goes through `service`, with the
job handed in, so the command line and the web run one code.

A viewer asks by name and gets one page at a time: a run as it is opened
(identity, policy, raster dpi, its pages, whether the book has truth), a
page as the builder's own data pass gives it, the scan's page as an image
at a bounded dpi, one block's crop (the read run's own where it kept one,
else cut from the scan), and the contour metric's pairs on the page. The
pairs are the metric's, one list for the sheet and the number, with each
pass's partner recorded and one verdict per model box: `books overlay`
draws from `src/booksmith/datasets/metrics/contour.py:page_pairs` and so
does the viewer. The truth side of that list -- the truth blocks, their
anchors, the diagnosis of a miss -- is served only to an admin; a user gets
the number's words on the run's own boxes.

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

Truth carries what it knows and says what it does not: `meta.text_marked`,
`meta.order_marked` and `meta.labelled` are three-state, and a missing flag
means "not said", never "yes". A truth drawn page by page says `labelled` on
every page, and once any page says it the contour metric compares only the
pages that say yes, and reports the three counts. Table truth is
`meta.artifact_truth[block_id]` as rows,
columns and cells; OTSL is what the model returns, not what truth stores.
Objects the annotators saw but the vocabulary cannot express stay in
`meta.out_of_scope`, so a box the model puts there is not counted against it.

## Measuring

A metric declares what it `needs` from the pair of bench and run: `truth`,
`pages`, `pdf`, `content` (the truth carries characters), `read` (the run
does). It runs only where its needs are met, and the table says why it did
not otherwise. It returns a record of scalars. A scalar carries its value,
the count behind a share, the coverage it was measured over with its unit,
the same quantity at each page or block that made it, keyed by anchor, and,
when the value is null, the reason. A null without a reason cannot be
constructed. Each scalar's declaration says where its values sit, a page
or a block of which side, and what its coverage counts, so a client places
a number where it was counted without knowing the metric; the contract
holds every record to its declaration.

A record names the identity of the run it measured and the hash of the
scan, out of the run's snapshot, so a results file can say later whether
the run on disk is still the one measured: current, stale, or not recorded,
and not checked where the run is not here to ask. The report refuses a
stale record as it refuses a dirty commit, and says the counts of the
rest. A results file is named for its bench and run, prefixed `processed-`
for a book under `processed/`, since the two roots can hold one name, and
a measure of a page set is a file of its own name with the pages in its
header, never the book's file: `books bench all --pages`, and the web asks
one page at a time.

Every metric has probes of deliberately spoiled input, in a module of their own
beside it, and the number must fall on each before the metric is believed:
`books bench selfcheck <book>` runs them on any bench, and one case per probe
runs in the suite. Which metrics exist and what each needs: `docs/metrics.md`.
Every number: `METRICS.md`.

The benches, and how each is rebuilt:

| bench | truth | rebuilt by |
|---|---|---|
| `slovar`, `spravochnik`, `matematika`, `atlas`, `katalog`, `zhurnal` | drawn, exact: characters, grids, ink | `books synth --book <name>`, byte for byte |
| `annopage` | real pages, objects by librarians, no text | `books annopage raw/annopage` |
| `hard` | the distillate of annopage: same-label neighbours side by side | `books subset` |
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
library is the engine of that application, `service.py` its door. Seams
still to cut, each a refactor of what exists:

- A run snapshot that stores each knob's name and value and points at the
  registry for its description, instead of carrying the description text.

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
| policy | a model's labels mapped onto the classes, each of which carries one of the three roles |
| role | text stays in the flow, an artifact becomes a picture, furniture is marked |
| run | one model over one book, under one label, with its snapshot |
| trait | a fact truth declares about itself per page: text marked, order marked; three-state |
