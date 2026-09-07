# Clean slate: the plan

Written 2026-09-06 from the audit, revised the same day after three skeptical
reviews (feasibility against the tree, design, knowledge loss) and again on
2026-09-07 after a fourth. Every objection was adopted; what each one changed
is in the text below and in the code, which is where a decision belongs, and
the two inventories they produced are at the end of this file. Every step ends
with a skeptical review before the next begins, and what that review found
goes in the commit message of the work it reviewed.

## Decisions this plan rests on

1. **Three layers, one rule.** `core` beneath, `processing` (module 1) and
   `datasets` (module 2) above. Imports go `cli -> datasets -> processing ->
   core`. Nothing in `processing` imports `datasets`. `remote` is imported
   only by `processing/*/rented/*`, `cli/rent.py`, `cli/doctor.py` and the
   `--rent` branch of `read`. Tree instruments (`cyr`, `prose`, the import
   graph) live in `booksmith.tree`, importable by the mutation battery;
   `tools/acceptance.py` and its siblings stay as thin
   command wrappers over them. A test over the import graph enforces the
   rule and exists from step 1.
2. **One book directory** for pipeline books and benches. A bench is a book
   directory that also has `truth/`. Runs are subdirectories under a label:
   `detect/<label>/`, `read/<label>/`. The label defaults to the adapter's
   `label()`: a filesystem-safe short name of the MODEL, declared by every
   adapter and carried in its fingerprint (doclayout takes it from the
   weights' `Global.model_name`, so `PP-DocLayoutV2`; yolox from the weights
   file stem; docling from its variant, `docling-heron`; the paddle reader
   from `MODEL_NAME`, so `PaddleOCR-VL-1.6-0.9B`). Never the adapter's
   registry name: `doclayout-onnx` is one adapter serving three models, and
   the tree's fingerprints today put `paddleocr-vl` in `reader` and the model
   in `model`. `run.json` carries `identity`: sha256 over the fingerprint
   taken before the page loop, with run-born keys (docling's `summary`) and
   machine-local values (`weights_dir`) excluded, plus the values of every
   knob the run read, `VLM_SEED` included. A command that would write a
   different identity under an existing label refuses and asks for `--run`.
   A run cut short by Ctrl-C or `--pages` is unsealed; it resumes under the
   same identity by today's `read_with.json` rule and is `Unmeasurable`
   until sealed; a detect run under an existing label with `--pages` refuses
   unless `--run` names a new label. A command that needs one run and finds
   zero or several refuses and lists the labels. `manifest.json` at the root
   is written by the first command that creates the directory and carries
   `source: {path, sha256}`; every later command refuses when the PDF on disk
   hashes differently. Pipeline books live in `processed/<name>/`, benches in
   `bench/<name>/`. `bench/real/` becomes one book directory per PDF, without
   `truth/`: a book, not a bench, and `bench score` refuses it; its page
   selector `holdout20.pages.json` stays beside as `pages.json`.
   `tests/expected/` and `results/` are not books and `Book.open`
   refuses them (no manifest). `bench/*/html/` is a stale build and is
   deleted, not migrated; `check.pdf` and `check/<model>.pdf` become
   `look/<label>.pdf`.
3. **The repair rule, reworded:** a repair is a reading, and it is journaled;
   nothing in the measured path is repaired. A raw read run is sealed when it
   ends (`run.json.pages_sha256` over `pages/` and `answers/`); nothing writes
   into a sealed run. A correction produces a derived run `read/<label>+c1/`
   with `run.json.derived_from` and its own `corrections/` records; the bench
   measures the raw run unless told the derived label. What stays forbidden
   and stays enforced where it is today: merged boxes, sniffed kinds, a retry
   of a 200, a re-ask inside a raw run.
4. **Definitions the rule needs.** A question is a re-ask iff its Ask is a
   function of a Said for the same anchor; forbidden in a raw run. Two
   readings are independent iff both Asks are fixed by their `run.json`
   before the first request, each run has its own directory, and neither
   driver reads the other's answers. `consistency` is agreement between two
   independent runs whose identities differ (in `VLM_SEED` at a temperature
   above zero, or in reader or model): two runs of one identity are one
   reading twice and are refused. The measurement it rests on, 217 of 270
   cells identical across three readings at temperature 0.4, is repeated as
   three runs at three seeds. Agreement, never accuracy. A correction is a
   re-ask by construction and is admitted only because it never overwrites,
   is recorded with its trigger, and is measured as its own run.
5. **No backward compatibility.** Module paths, command names, directory
   layout and snapshot fingerprints change. Tracked bench data moves by
   `git mv` with a sha256 list before and after. An expected snapshot whose
   input moved is regenerated in the same commit, with the diff read and the
   reason written. Unreproducible data (`processed/*`, `bench/*/dots*`) is
   copied before it is migrated and the copy is kept until the migrated tree
   proves equal on the reports.
6. **Claims are re-measured, not copied.** A number, a date, a configuration
   or a rejected alternative stays beside the constant or guard it bought,
   however long that makes the comment. Only narrative moves ("here stood",
   "used to say", the first edition). Where a doc claim disagrees with a
   measurement on this tree, the measurement wins.

## Invariants that hold after every commit

* `tests/run.py` green; `tests/run.py --slow --selfcheck` green (114 s: it is
  a per-commit invariant, not a weekly one, because 209 `attrs()` mutations
  abort the battery on the first moved attribute and nothing else sees it).
* `tools/anchors.py` lands every mutation, including the `attrs()` patcher it
  learns in step 0.
* `tools/acceptance.py` prints `same` for every report, or the report was
  regenerated in that commit with `--save` and the reason in the message.
* `tools/figures.py` and `tools/layout.py` hold: no measurement restated in
  a second document, no path outside the declared shape of a book.
* `bench/` and `processed/` are never scratch space; tests build in temp dirs.
* One commit per coherent move on `chistyy-list`; nothing is pushed.

## Baseline, measured 2026-09-06 before the first change

Checks 304, mutations 286 caught 286 in 114 s, anchors 73, acceptance 7 same,
slovar rebuild byte-identical, fitness on annopage 1230 objects with 2 warned
inkless against score's 1232. Every commit since carries its own numbers on
its last lines; compare against those, not against this.

## Step 0: locks and instruments

* `tests/expected/*.json`: the raw result dicts of `metrics.compare` on
  annopage and hard, `text.measure` on slovar truth against itself,
  `fitness.measure` on slovar, floats rounded to 6 places; each file records
  the sha256 of the truth directory and the `manifest.json` it was taken
  against. `acceptance.py` diffs them key by key at 1e-6.
* `tests/expected/score-selfcheck.txt` and `fitness-selfcheck.txt`: probe
  names are the only lock on the batteries and only text has one today.
* `tools/anchors.py` learns `attrs(<name>, k=...)`: resolve `<name>` through
  the battery's import block and assert `hasattr`.
* The slovar truth sha256 list, scoped to `truth/*.json` only: the manifest
  will change (generator file, sha, commit marker, knob text) and that diff
  is read and written up, with the `case` names asserted unchanged.
* Journal: baseline, plan review.

Skeptic checks: perturb `COVER_MATCH`, run acceptance, see red, revert; the
new anchors patcher reports a count and goes red on a renamed attribute.

## Step 1: core

Goal: the floor both modules stand on, and the end of the copies.

| moves to `core/` | from |
|---|---|
| `page.py`: Block, Page, KINDS (from apply), `ours_order` (from base) | `models/base.py` minus Recognizer, `doc/apply.py:35-38` |
| `book.py`: ASSETS, SOURCE, journal path (Book.open arrives in step 3b) | `doc/html.py:47-49`, `run/replay.py` |
| `knobs.py`, `stamp.py`, `replay.py` | `run/` |
| `raster.py`: the whole of `doc/crop.py` (`cut`, `params`, `native_dpi`, `EPS_PT`, `_box_trouble`, `box_to_points`) plus `open` and `render(page, dpi)` for every `get_pixmap` on the read path; `html.py`'s `sha256_crop_code` hashes `core/raster.py` from the same commit | `doc/crop.py` |
| `policy.py`, `order.py`, `otsl.py`, `schema.py`, `config.py` | the root |
| `textnorm.py`: `normalize`, `norm_note`, `NORM_REFUSED` with its numbers | `text.py:75-217` |
| `errors.py`: `BooksmithError(Exception)`; `Refusal` (rc 1, one line); `Unmeasurable` (rc 2); `WeightsMissing(Unmeasurable)`; `MetricError`, `TextError` under `Unmeasurable`; the other per-module classes under `Refusal` | 12 per-module classes, 3 WeightsMissing, 59 convertible `raise SystemExit("...")` |
| `log.py`: one `log()` to stdout with a timestamp, import-free; its header keeps `ledger.py`'s reason (a command that rents nothing must not import `vastai`) | 4 mergeable copies of 6; the two box entrypoints keep a local one and say why |
| `tree/cyr.py`, `tree/imports.py` (the dependency rule as a test) | `cyr.py`; new |

Rules kept from the reviews: `stamp.sha256` and `stamp.commit` become the
only ones (8 file hashers deleted; `apply._sha256` hashes text and stays;
`replay._sha256` returns None on OSError and stays); every path built from
`__file__` by `dirname` chains is audited and tested on the moved tree
(`read/run.py` otsl hash, `stamp` root, `ledger._ROOT`, `knobs.SRC`,
`cyr.ROOT`, `paddleocr_vl.PKG`); `raster.py` catches `Refusal` where
`crop.py:148-151` caught `SystemExit`; `UnknownLabel` goes under
`Unmeasurable` (a label outside the vocabulary during `bench score` is
"could not count"); `dots_ocr/entrypoint.py` keeps `SystemExit` because
it runs on the box without the package, and `test_parse_pages` names both
classes as "refusal aloud"; `paddleocr_vl/entrypoint.py` catches
`BooksmithError` at its main and exits 1 with one line; `cli._tool_errors`
becomes `except Unmeasurable` and `except Refusal`; the residue declaration is re-keyed
in the same commit; the pymupdf rule is "no rendering outside
`core/raster.py`", and the writers (synth, djvu, annopage, subset, overlay)
keep their pymupdf.

The migration script carried the old-to-new table, resolved every
relative import to an absolute name against the old package by ast (104 in
src), maps it, re-emits, and rewrites `tests/support.py`, the battery's
`COPY`, `sources(...)`, `one_line(...)`, its import block, and every
`from booksmith` line in tests and tools. It prints its counts. The table
maps SYMBOLS, not only modules, for the five modules step 1 splits:
`models/base` (`Block`, `Page`, `ours_order` to `core.page`; `Recognizer`
stays), `text` (`normalize`, `norm_note`, `NORM_REFUSED` to `core.textnorm`;
`measure`, `TextError` stay), `doc/html` (`ASSETS`, `SOURCE`, `journal_path`
to `core.book`), `doc/apply` (`KINDS` to `core.page`), `doc/crop` (whole).
A module alias is rewritten by which attributes it uses, in tests and in the
battery alike: `attrs(ap, KINDS=...)` becomes `attrs(page, KINDS=...)`
because the test that catches it imports `KINDS` from `core.page` now.
`test_models_contract` builds module names from strings and matches the
name `Recognizer` by text; it is edited by hand. CLAUDE.md's cited paths
are updated in the same commit because `test_docs_map` chases them.

The `__file__` checklist, each tested on the moved tree: `config.py` ROOT
(`..`, `..`: one level deeper it points at `src/` and every secret reads as
unset), `schema.py` ROOT (three `dirname`s: every glob counts zero),
`acceptance.py` ROOT (three), `cyr.py` ROOT (three), `read/run.py` (the
`otsl.py` hash and the `run.py` self-hash, renamed to `driver.py` in 3a),
`doc/html.py` (`sha256_crop_code` beside a crop that left; `MATHJAX`, so
`doc/mathjax/` travels with html.py), `paddleocr_vl.PKG` (two up),
`knobs.SRC` and `replay.PKG` (two up, same depth after the move, tested
anyway), `stamp` (from `booksmith.__file__`, safe by construction),
`ledger._ROOT` (stays). `doc/html.py` writes `"module":
"booksmith.doc.html"` as a literal; it becomes `__name__`, or every build
snapshot reads "writer not identified" after the move. `core/replay.py`
gains a `RENAMED` table from the migration so the three tracked detect
snapshots that name `booksmith.models.doclayout` still verify by module
name; `replay-annopage.txt` is regenerated in 3a for that line and says so.

Skeptic checks: the comment text of every moved file diffs empty against
its source except for the header lines named in the commit; the slow battery
is green; `tree/imports.py` is green and goes red on a planted upward import;
`_tool_errors` maps every custom class; no `dirname(dirname(` chain remains
untested.

## Step 2: datasets

Goal: a Bench you can open, a Metric that returns a Record, one battery
runner, one table.

* 2a `datasets/bench.py`: `Bench.open(path)` (name, pdf, truth dir, manifest,
  sha256, `traits()` per page in three states, `pages("truth")`), `Run`
  (a pages dir plus its `run.json`, required; `vocabulary`; `derived_from`).
  Replaces `metrics._load`, `text._load`, `cli._page_files`, `text._pages`,
  `overlay._same_book`, `fitness`'s borrowing. One identity check. A pages
  directory without `run.json` beside it is `Unmeasurable`.
* 2a `datasets/metrics/base.py`: `Record` (metric, bench, run, scalars,
  params, detail) where a scalar is `{value, over: {n, of}, why}` and value
  is null only with a non-empty why; `Metric` (`name`, `needs` for
  prerequisites only: pdf, truth, pages, content; `run`, `report`, `battery`);
  `Probe(name, want, fn)` returning `Outcome(caught, note)`; `run_battery`
  keeping the denominator from printed outcomes, the "rest of the battery did
  not arrive" catch, threshold restore in `finally`, the "what this battery
  does NOT catch" line per metric, and fitness's paired demand; `mutate.py`
  with the shared mutators.
* 2a `datasets/metrics/contour.py` (metrics.py), `text.py` (text.py),
  `fitness.py` (the Metric and the battery, `mutations` and its mutators,
  over `processing/assess/ink.py`, which holds the MEASUREMENT: `measure`,
  `report` and their helpers, one implementation, born in this step),
  `snapshot.py` (over `core.replay.check`), `assembly.py` (column jumps,
  `needs={"pages"}`). The battery alias `fit` splits in two: the
  measurement-side patches point at `assess.ink`, the battery-side at
  `metrics.fitness`; `test_fitness`'s `fitness.INK == synth.INK` is
  re-pointed here and again in 2c. Thresholds stay module constants and ride into
  `Record.params`; `fitness._at` and the battery's `attrs(fit, INK=...)`
  keep working.
* 2a `datasets/table.py`: `applicable(bench, run)`, rows as (bench, run,
  metric, scalar); `bench all <bench> [--run L] [--json PATH]` writes
  `results/<bench>-<label>.json` by default and prints one table where
  a null value prints its why as a footnote;
  `datasets/accept.py` (from acceptance.py) diffs Records at 1e-6 and still
  diffs the prose; `datasets/look.py` (from overlay.py), which must also draw
  a single run on a book without truth.
* 2b Tests: `test_metrics_contract.py` (every Metric obeys the protocol; every
  scalar has a why when null); the three battery tests fold onto
  `run_battery`; the probe names printed are unchanged (expected files).
* 2c `datasets/make/`: `synth/` (`draw.py` primitives, `age.py`, `truth.py`
  ink measurement and text-layer check, `__init__.py` for the build, `books/` six modules with
  `spravochnik` extracted), `annopage.py`, `subset.py`. Synth writes
  `order_marked`. Proven by rebuilding all six synthetic benches: truth files
  byte-identical to the step-0 list; manifests regenerated and their diff
  written up. The write-aside dance is left as it is.

Skeptic checks: `tests/expected/*.json` equal the Records' scalars to 1e-6;
truth byte-identical after 2c; uncaught counts per bench unchanged (fitness
is red by construction on slovar, matematika, zhurnal); `bench all` on
annopage prints one table and the JSON round-trips; no upward import.

## Step 3: processing, the book directory, the command line

Split in three because the audit's step 3 fused four independent risks.

### 3a Moves, names unchanged

| moves to `processing/` | from |
|---|---|
| `extract/djvu.py` | `djvu.py` |
| `layout/base.py` (Detector, formerly Recognizer), `layout/registry.py` (one table: name to class, vocabulary, fingerprint model name), `layout/detect.py` | `models/base.py`, `detect.py:57-109` |
| `layout/adapters/{doclayout,docling,yolox}.py` | `models/{doclayout,docling_heron,yolox_layout}.py` |
| `layout/rented/dots_ocr/` | `models/dots_ocr/`; its image constants go to `remote/image.py` so it stops importing a reader |
| `read/__init__.py`, `read/driver.py` | `read/__init__.py`, `read/run.py` |
| `read/transports/openai_http.py` | `read/http.py` |
| `read/readers/paddleocr_vl.py` | `models/paddleocr_vl/reader.py` |
| `read/rented/paddleocr_vl/` (spec, entrypoint, run.sh, constraints, requirements) | `models/paddleocr_vl/`; `PKG` computed from `booksmith.__file__`, and a test that `spec()` ships every package directory |
| `assess/ink.py` | `fitness.py` (see 2a) |
| `assemble/{html,swap,apply}.py`; `doc/feed.py` is deleted except `_union_area`, which moves into `html.py` | `doc/{html,swap,apply}.py`, `doc/feed.py` |

Policy and order tables stay in `core`; an adapter names its vocabulary.
`VLM_INPUT`, `MASK_FILL`, `FEED_DPI` are deleted: no reader on the paid path;
their record (the blank-sheet invention, the isolated column, the token
ceiling against the longest block) goes verbatim to
`docs/lessons-from-deleted-code.md` and a five-line note stays beside
`books crop`; "eight empty defaults" in knobs.py becomes seven;
`replay-annopage.txt` regenerated with the reason (the knob deletions and
the adapter module line). `books crop` is `read/driver.py` in preview: the
same `crop_dpi_for`, the same `raster.cut`, and there is no second crop
path. Not "a transport that answers nothing", as this line first said -- a
stand-in transport would have to invent a fingerprint, and that fingerprint
would be written into `read_with.json` for the next paid run to compare
against. A preview has NO transport and writes neither that file nor
`pages/` nor `answers/`. The crops sit beside the run for now; step 3b puts
them under `read/<label>/crops/` with everything else.
`readers()` re-checked after the move because it walks the tree by path.
CLAUDE.md's cited paths follow in the same commit.

### 3b The book directory and Book.open

* `core/book.py`: `Book.open(path)` for a book directory or a bare PDF (creates
  `processed/<safe-name>/` by today's `book_home` rule and writes
  `manifest.json` with `source.sha256`); `book.runs("detect")`,
  `book.run("detect", label)`, `book.build`, `book.journal`;
  `build/run.json` records `read_run` label and the sha256 of its `run.json`,
  and `apply`, `assess`, `correct` default to it.
* Data migration, one script `tools/migrate_book.py`, run on a copy first:
  `bench/*/detect/` to `detect/<label>/` (`git mv` for tracked `run.json`,
  plain move for local pages), the two dots page sets (`annopage-lite`,
  `hard36`; 636 tracked, sha256 list before and after) to
  `detect/dots-ocr/pages/` with a `run.json` written from the pages' own
  `meta` (`detector`, `downscale`, `reading_order`) carrying `builder:
  absent` and no fingerprint, so that `Run` opens them for measurement and
  `replay --check` refuses them; the raw dots job output (`job.log`,
  `pass0/`) to `detect/dots-ocr/job/`; `bench/real/*.pdf` to one book
  directory each; `processed/ogneupory-vl2` and its two siblings to
  `detect/ read/ build/`. `bench/*/html/` deleted (stale untracked builds);
  `check.pdf` and `check/` to `look/`.
  `.gitignore` (`bench/*/detect/*/pages/` and friends), `core/schema.py`
  globs recounted and the recount printed, `datasets/accept.py` commands,
  `bench/README.md` follow in the same commit, and `git status` is checked
  for un-ignored pages before the commit.
* `hard`'s manifest gains `derived_from` with the sha256 of every source
  truth file; `hard36` and `annopage-lite` manifests say `builder: absent`.
* Raw read runs are sealed at the end of `books read` (`pages_sha256`).

### 3c The command line

`cli/` package: `__init__.py` (main; `Refusal` rc 1, `Unmeasurable` rc 2,
argparse usage 64), `book.py`, `bench.py`, `rent.py`, `doctor.py`;
`pyproject.toml` follows; `test_docs_map` and `test_models_contract.DRIVERS`
follow.

```
books doctor | offers | ls | down ID | reap | ledger
books prepare X.djvu [--out DIR]
books detect  <book|pdf> [--run L] [--pages ...]
books crop    <book> [--detect L] [--pages ...]        free: what read will send, through read's own path
books read    <book> [--detect L] [--run L] [--pages ...] [--rent --gpu --max-dph --machine | --dry-run]
books build   <book> [--read L]
books apply   <book> [--anchor A --file F | --undo A | --status]
books assess  <book> [--read L] [--against L2] [--judge]           (step 4)
books correct <book> --anchor A [--read L] [--reader R] [--param k=v]   (step 4)
books replay  <book|dir> [--run L] --check | --selfcheck
books look    <book> [--run L] [--truth]
books bench make synth <book> [--cases ...] | annopage <root> [--split test|train] [--limit N] [--truth-only] | hard [--from a,b,c]
books bench score | text | fitness | all  <bench> [--run L] [--json PATH]
books bench accept [--save NAME ...]          the report and record table, not one bench
```

`feed` is gone (`crop` is the free verb; no free flag on the paid verb);
`html` is `build`; `synth`, `annopage`, `subset` are `bench make`; `score`,
`text`, `fitness`, `overlay` are under `bench` or `look`; `--split` on
`prepare` is `--spreads`; `--key` is `--ssh-key`; `pages` is only ever a
selector. `help.txt` regenerated.

Skeptic checks: `books detect bench/slovar` into `detect/PP-DocLayoutV2/`
reproduces the moved pages by sha256; acceptance regenerated only for
reports whose paths or command names changed, and their diffs hold only path,
fingerprint and label lines; `replay --check` on the moved annopage run
explains every missing key; `apply --status` on the migrated book unchanged;
`spec()` ships every package; no rendering outside `core/raster.py`; the
import graph green.

## Step 4: assess, correct, judge

Tested against the fake VLM only; nothing here spends money without the
owner. The judge is a second paid command and goes through the ledger and
`doctor` like `read`.

* 4a `processing/assess/`: one table per anchor over `answers/*.json` and
  `blocks.json` (the five zeros, `hit_ceiling`, `kind_not_as_promised`,
  `crop_dpi_reason`, `clipped_by_sheet`, `delivery_attempts`,
  `answer_wrong_anchor`, `otsl_grid` shape counters, `repeats`), the page
  table from `ink.py` over the detect run, the run tally; `consistency(run_a,
  run_b)` computed from two independent runs (CER between contents; cells by
  address for OTSL). `PASSES` is deleted: two labels replace it, and the
  measurement that justifies the signal (217 of 270 cells at temperature 0.4)
  is cited beside `consistency`. `LOGPROBS` gets its reader: the transport
  asks for them when set and `assess` carries a confidence column labelled
  "words, not numbers". `books assess` writes `assess/<label>/table.json` and one
  table; `blocks.json` carries `assess` per anchor.
* 4b `processing/read/reread.py`: `books correct` builds one new Ask, sends
  it, writes `read/<label>+cN/corrections/<anchor>/<n>.json` (Ask with params
  and image sha256, Said, trigger and its value, reader and transport
  fingerprints) and the derived `pages/`; the write is atomic in the
  `save_journal` pattern; the raw run is never written. Tests: the raw run's
  hash is unchanged after a correction; `bench text` on the raw run returns
  the same Record to 1e-6 before and after; a pages dir without `run.json`
  is `Unmeasurable`; a Said without a record cannot exist; a battery probe
  goes red when a corrected NUMBER is written into `content` (the first
  enforcement of "numbers only flagged").
* 4c `read/transports/anthropic_http.py` (Messages API; key from `.env`;
  `check()` over the models list; a 200 never repeated) and
  `assess/judge.py`: the judge owns a Transport and builds its own Asks;
  `Ask.context: tuple[str, ...]` carries the candidate text after the image;
  the verdict is stored under `assess/<label>/judge/<anchor>.json`, raw
  beside parsed, never in `content`; non-JSON verdicts are their own
  counter. `tests/fake_vlm.py` grows a judge plan and a Messages-shaped
  endpoint.

Skeptic checks: the four tests of 4b; every assess column has a probe that
goes red on a corrupted input; `consistency` refuses two runs of one
identity; the judge never retries a 200; the ledger records a judge run.

## Step 5: documentation

Goal: five kinds of text in five places, guarded.

* `CLAUDE.md` under 100 lines: the tree, the dependency rule, the rules by
  name, how to run the tests, where each kind of text lives.
* `README.md`: install and the five-command journey.
* `docs/reference/`: `formats.md` (Page, run.json, manifest, answers, blocks,
  swaps, assess, corrections), `commands.md` and `knobs.md` generated by
  `tools/gendocs.py` with a test that they are current, `extending.md` (one
  checklist each: detector, reader, transport, assess column, metric, bench).
* `docs/rules.md`: the rules, one measurement each, and the file:line that
  enforces each.
* `docs/results.md` generated from `results/*.json` written by
  `books bench all`.
* NO JOURNAL DIRECTORY. One stood here for a week and was deleted: measured
  over eleven entries, not one figure in it was absent from the commit
  messages and the documents, and the reasoning it held was either already in
  the code or belonged in `docs/rules.md`. Narrative lives in commit messages
  -- git keeps them, attached to the change they describe, and this project
  writes them long on purpose. A document describes the tree AS IT IS; a
  commit message describes how it got that way. `lessons-from-deleted-code`
  is the one exception and stays: it holds what code that NO LONGER EXISTS
  measured, which no present-tense document can carry. The lessons that are
  rules (chain budget, `iid` after return, `cost is None`, the loop
  detector's 125 to 0, the 255 byte name, the date beside a number) are cited
  from the code that needs them in step 4.
* Comments in code, per package: a module header states what goes in and
  what comes out; a measured table stays beside the constant it bought, at
  any length; narrative goes to the commit message, and the rule the
  narrative encoded stays in one sentence beside the code (the inventory of
  those rules is at the end of this file). `tree/prose.py` measures the ratio
  per package the way `tree/figures.py` counts restated measurements, with
  `tools/prose.py` as its command.
* `tests/test_docs_map.py`: the four-literal number ban is already the
  general instrument (`tree/figures.py`, ceiling 25); step 5 takes the
  ceiling to zero and the check turns from a ratchet into a ban.
* A table mapping the six transliterated bench names to their meaning; the
  directories keep their names because `hard/manifest.json` pins them.

Skeptic checks: every rule and every price-of-a-mistake note from the
review's inventory is findable in the new tree; the generated docs match
the tree; no reference doc cites a journal entry as a rule; the prose ratio
fell and the baseline is tracked.

## Claims settled so far

* "33 probes" in the contour battery: TRUE (the audit's static 28 was wrong).
* "1232 vs 1230": both right; fitness warns about two inkless objects.
* The synthetic bench is deterministic: 13 of 13 truth files and the PDF
  byte-identical on rebuild.
* The manifest's generator guard has been red since f92b55a9 (sha of
  synth.py 4df641ff in the manifest against e0273f3c in the tree) and nothing
  noticed: a record, not a guard. Regenerated in 2c.
* "Six rules", "six paid commands", "the instruments print Russian", "1103
  characters", "three ways over": corrected in step 5 with the measurement.
* The plan's own first edition said ~90 SystemExit, 15 classes, 9 sha256, 6
  logs: the tree says 74 (59 convertible), 12, 8 replaceable, 5 mergeable.

## Order and size

Steps 0, 1, 2a-2c, 3a-3c, 4a-4c, 5: about fourteen commits. The riskiest
is 3b, the on-disk migration; it runs on a copy first and the copy stays
until the reports agree.

## Two inventories, for steps 4 and 5

Working checklists out of the plan review, not a record of it: the first is
what step 5 may not lose when it moves prose, the second what step 4 may not
break when it adds the first enforcement of the reworded repair rule.

### Narratives that encode a rule (keep the rule beside the code)

* A truth trait absent is "not said", never defaulted (`metrics` header).
* One named gate over box candidates; no `default=` over them (`metrics`).
* Jumps compare by count; a quantity prints its ruler's parameters.
* Summary numbers are blind to dpi; compare per page and per label (PAGE_DPI).
* Counts are printed by `readers()`, never typed; debt is a field (`knobs`).
* A measurement names the adapter sha it was taken with (DOCLING_PIPELINE).
* Knob text rides into `run.json` and must be true; an empty default is not passed on; the registry default equals `run.sh`'s `${X:-...}`.
* One snapshot shape: `knobs/NAME/value`.
* onnxruntime and cv2 stay lazy imports (box importability) (`stamp`).
* The package root comes from `booksmith.__file__`, never from counting `dirname`s (`stamp`; the exact case this plan creates).
* One dirty-tree marker string across all writers.
* Empty `CROP_DPI` means native, else the detection dpi; "0" refused; one `EPS_PT`; native asked only when dpi is not named; clipping measured on the raw box (`core/raster`).
* Alien pages refused; resume compares `read_with.json`; answers keyed by anchor; "asked" counts real questions; transport knobs credited to the transport (`read/driver`).
* Parse failure is separated from delivery failure; `delivery_attempts = attempt + 1` (`http`).
* The returned trouble word equals the attribute name (`assemble/html`).
* One assembly rule; 474 and 453 are historical and never cited as current (`order`, `docling`).
* Battery seams are module-level (a staticmethod put back by setattr is a function) (`doclayout`).
* `t0` from run start; guards at module level; signals restored in `finally` (`runner`).
* Dead-man on the machine; ARMED reported in quantities; grace validated as a number; ASCII only through the API (`vast`).
* Socket path under 108 bytes; `deadman="not checked"` is a value (`box`).
* No CUDA default; three filters survive `machine_id` (`spec`).
* Annotations are not pages; sweep aside files; do not restate unverifiable provenance (`annopage`).
* Traits travel and are counted by name; no second guard (`subset`).
* Every `insert_textbox` checked; truth carries characters and grids (`synth`).
* Content at the gutter means no cut; count landscape sheets (`djvu`).
* Name from code, count from disk; reports compared whole; "snapshot old" is not "incomplete" (`schema`, `acceptance`, `replay`).
* Three knob roles; four loud failures (`detect`).
* One `parse_pages`; every passthrough knob has a box flag; setsid; trap; liveness before curl (entrypoints, `run.sh`).
* Refused normalisation steps are recorded with their numbers and travel with `normalize` (`textnorm`).
* `fitness.INK` is knowingly a second copy of `synth.INK`, held together by a test; never merged by import.
* A vanished consumer means removal, not debt (`knobs`, PADDLE_PDX).

### Enforcement points, to be kept through every move

Nobody repairs the model: `read/transports/openai_http.py` (200 never repeated; body parse separated from delivery; 4xx breaks), `read/__init__.py` (no re-ask), `read/driver.py` (`_sniff` decides nothing; bytes unedited), `core/raster.py` (negative margin refused), `knobs.py` (0 is a value; six patch knobs deleted on purpose), `order.py` (list order only), `layout/adapters/docling.py` (vendor code unedited, knob default off), `layout/base.py` rule 1, `datasets/make/subset.py` (`_carry_meta` refuses overwriting truth). What was recognised is untouchable: `Said` fields, `data-*` on our wrapper, `repeats_on` hides for display only. A metric must fail: the three batteries, `knobs.audit()`, the battery seams, `tools/anchors.py`. The zeros: `read/driver.py` tally printed always, `cli._page_files` two reasons, `crop.native_dpi` None as a value, `knobs.number` refusing nan, `box.deadman` "not checked", the batteries' "no data" against "NO". A knob is declared: `knobs.knob` raising, `detect._knob_roles`, the entrypoints' passthrough. Snapshot complete and in effect: `snapshot_with_readers`, `read_with.json`, `replay._base`, `detection.sha256_snapshot`, `sha256_otsl_parser`. Same book by sha256: `read/run`, `assemble/html.build` before and after, `metrics._same_book`, `overlay._same_book`. Foreign pages refused: `detect`, `read/run`, `html` journal guard. Nothing half-built survives: the three write-asides. Exit codes carry meaning: `cli.main`, `doctor` per adapter, `tests/run.py`, `runner`, `run.sh`.
