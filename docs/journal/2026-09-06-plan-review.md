# 2026-09-06: three skeptics against the plan, and what each objection did

The first edition of `docs/plan.md` went to three reviewers with different
briefs: feasibility against the tree, design against the vision, and
knowledge loss. Their objections are listed here with the outcome. ADOPTED
means the plan changed; REFUTED means the plan stands and says why.

## Feasibility

| objection | outcome |
|---|---|
| The rename script targets 4 absolute imports; src has 104 relative ones whose meaning changes with depth | ADOPTED: `tools/migrate_layout.py` resolves relative imports by ast against the old package and re-emits absolute ones; prints its counts |
| 209 `attrs()` mutations abort the battery on the first moved attribute; `tools/anchors.py` sees only `one_line` and `sources`; nothing in the invariants runs the slow battery | ADOPTED: the slow battery (114 s) is a per-commit invariant; anchors learns the `attrs` patcher in step 0 |
| "No pymupdf outside raster.py" is impossible: synth, djvu, annopage, subset, overlay write PDFs and draw | ADOPTED: the rule is "no rendering outside `core/raster.py`"; writers named |
| Thresholds as knobs: every old snapshot becomes "missing", `fitness._at` and `attrs(fit, INK=...)` turn into no-ops, `number()` reads the environment per call in hot loops | ADOPTED: thresholds stay module constants and ride into `Record.params` |
| `cyr.py` leaving src contradicts its own reason (the battery imports it) | ADOPTED: `booksmith.tree.cyr`, importable |
| `processed/ogneupory-vl2` migrated in place is one-way on unreproducible data | ADOPTED: copy first, migrate the copy, prove `apply --status`, keep the copy |
| `spec()` computes `PKG` two `dirname`s up and would ship a partial package silently | ADOPTED: `PKG` from `booksmith.__file__`; a test that `spec()` ships every package directory |
| `SystemExit` to `Refusal` cannot reach `dots_ocr/entrypoint.py` (no package on the box); `test_parse_pages` classifies by class | ADOPTED: dots keeps `SystemExit`; the test names both classes; the paddle entrypoint catches `BooksmithError` at its main |
| CLAUDE.md is a tested artifact in steps 1 and 3 | ADOPTED: paths updated in the moving commits |
| Step 3 fuses four risks | ADOPTED: 3a moves, 3b layout and Book, 3c command line |
| Numbers in the plan were wrong: 74 SystemExit not ~90 (59 convertible), 12 classes not 15, 8 sha256 not 9, 5 logs not 6 | ADOPTED |
| "Four inversions" unnamed | ADOPTED: html imports text; html imports detect; replay imports html; the read contract imports apply; and cli takes its log from remote.vast |
| `doclayout` vs `doclayout-onnx` for run names | ADOPTED: the label is the fingerprint's model name |
| The slovar manifest's generator sha has been red since f92b55a9 and nobody noticed | RECORDED: it is a record, not a guard; regenerated in 2c |

## Design

| objection | outcome |
|---|---|
| Run directories named by adapter collapse V2, V3, plus-L, heron on and off the pipeline, and the two seeds consistency needs | ADOPTED: label = fingerprint model name; `run.json.identity`; refuse a differing identity under an existing label |
| `ink` implemented twice (datasets metric and assess signal) | ADOPTED: one implementation in `processing/assess/ink.py`; the datasets metric wraps it |
| `corrected/pages/` as a bare page set is measurable with the same-book guard off and under the raw run's name | ADOPTED: derived runs `read/<label>+cN/` with `derived_from`; `Run` requires `run.json`; raw runs sealed by `pages_sha256`; four tests |
| Upward imports left in place: read imports crop, the read contract imports apply.KINDS, replay imports html.ASSETS, dots imports paddle for an image name | ADOPTED: crop into `core/raster.py`, KINDS into `core/page.py`, layout constants into `core/book.py`, image constants into `remote/image.py`; the import-graph test exists from step 1 |
| `Signal.score(book, anchor)` cannot express per-page ink or two-run consistency; five of six signals are lookups | ADOPTED: assess is one table over existing observations plus `consistency(run_a, run_b)`; no Signal protocol |
| Judge as a Reader with a Route: a verdict is not a content kind and routes cannot carry the candidate text | ADOPTED: the judge is an assess column with its own Transport; `Ask.context`; verdict never in `content`; a second paid command through the ledger |
| Policy tables beside the adapter kill the cross-vocabulary contradiction check | ADOPTED: tables stay in core; adapters name a vocabulary |
| `needs: frozenset` and bare `None` scalars; traits are per page and three-state | ADOPTED: `needs` for prerequisites; scalars `{value, over, why}` |
| `read --preview` on the paid verb, `reading` three letters from `read`, no way to name a run, `snapshot` misnamed, the `rent` noun buys nothing | ADOPTED: `books crop`; `bench text`, `bench fitness`; `--run/--detect/--read`; `replay --check` kept; rental verbs flat |
| One `manifest.json`, not a separate `source.json`; `hard` gains `derived_from`; `bench/real` becomes book directories; `dots` migration missing | ADOPTED |
| Defer the synth split | PARTLY: the split stays as 2c, last in step 2, proven by byte identity; the write-aside dance is left alone |
| The "no pymupdf" invariant | ADOPTED as above |
| `PASSES` deleted, consistency takes two labels; the 217 of 270 measurement cited | ADOPTED |
| The definition of re-ask, independent readings, consistency, correction | ADOPTED verbatim into decision 4 |

## Knowledge loss

| objection | outcome |
|---|---|
| `WeightsMissing(Refusal)` flips rc 2 to 1, and `_tool_errors` lists classes by module string that would match nothing after the move | ADOPTED: `WeightsMissing(Unmeasurable)`, `MetricError`/`TextError` under `Unmeasurable`; `_tool_errors` catches the base classes |
| Paths from `__file__` break silently on the move (otsl hash in the read snapshot, stamp root, ledger, knobs, cyr, PKG) | ADOPTED: audited and tested on the moved tree in step 1 |
| `crop.py` catches `SystemExit` from `knobs.number`; batteries catch `Exception` | ADOPTED: `Refusal(Exception)`; crop catches it |
| One `log()` to stderr reorders every acceptance report (stdout + stderr concatenated); the box entrypoints cannot import core before `--pkg` | ADOPTED: log stays on stdout, import-free; the two entrypoints keep a local log and say why; `ledger.py`'s reason (no `vastai` import) kept in the header |
| The battery merge would drop the counting rules | ADOPTED: listed in 2a; probe names locked by expected files in step 0 |
| Deleting the three preview knobs deletes the recorded hypothesis and its counter-measurements | ADOPTED: record to the journal verbatim, five-line note at the preview, "eight empty defaults" corrected |
| The synth split and the commit merge change every synthetic manifest | ADOPTED: the lock is `truth/*.json` only; manifests regenerated, diff written, case names asserted |
| Fifteen-line headers erase measured tables (DOCLING_PIPELINE, order, docling, metrics, fitness, text, replay, schema, otsl, feed) | ADOPTED: a measurement stays beside its constant at any length; only narrative moves; the list of narratives that encode a rule is kept (below) |
| `cyr.RESIDUE` names 20 paths; re-key in the same commit | ADOPTED |
| The reworded rule has no enforcement yet; step 4 must add the first and keep every old enforcement point | ADOPTED: the sealing test, the derived-run test, the "corrected number into content" probe; the inventory of enforcement points is below |

## Narratives that encode a rule (keep the rule beside the code, move the story)

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
* Empty `CROP_DPI` means native, else the detection dpi; "0" refused; one `EPS_PT`; native asked only when dpi is not named; clipping measured on the raw box (`crop`).
* Alien pages refused; resume compares `read_with.json`; answers keyed by anchor; "asked" counts real questions; transport knobs credited to the transport (`read/run`).
* Parse failure is separated from delivery failure; `delivery_attempts = attempt + 1` (`http`).
* The returned trouble word equals the attribute name (`html`).
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

## Enforcement points of the rules, to be kept through every move

Nobody repairs the model: `read/http.py` (200 never repeated; body parse separated from delivery; 4xx breaks), `read/__init__.py` (no re-ask), `read/run.py` (`_sniff` decides nothing; bytes unedited), `doc/crop.py` (negative margin refused), `knobs.py` (0 is a value; six patch knobs deleted on purpose), `order.py` (list order only), `docling_heron.py` (vendor code unedited, knob default off), `models/base.py` rule 1, `subset.py` (`_carry_meta` refuses overwriting truth). What was recognised is untouchable: `Said` fields, `data-*` on our wrapper, `repeats_on` hides for display only. A metric must fail: the three batteries, `knobs.audit()`, the battery seams, `tools/anchors.py`. The zeros: `read/run.py` tally printed always, `cli._page_files` two reasons, `crop.native_dpi` None as a value, `knobs.number` refusing nan, `box.deadman` "not checked", the batteries' "no data" against "NO". A knob is declared: `knobs.knob` raising, `detect._knob_roles`, the entrypoints' passthrough. Snapshot complete and in effect: `snapshot_with_readers`, `read_with.json`, `replay._base`, `detection.sha256_snapshot`, `sha256_otsl_parser`. Same book by sha256: `read/run`, `html.build` before and after, `metrics._same_book`, `overlay._same_book`. Foreign pages refused: `detect`, `read/run`, `html` journal guard. Nothing half-built survives: the three write-asides. Exit codes carry meaning: `cli.main`, `doctor` per adapter, `tests/run.py`, `runner`, `run.sh`.

## Second pass, 2026-09-07

The revised plan went back to one reviewer with a narrow brief: are the
adopted rows really in the text, and does the text contradict itself. The
verdict was NOT READY, on eleven points, all taken:

* fitness's battery half cannot live in `processing`: the measurement goes
  to `assess/ink.py`, the Metric and its battery to `datasets/metrics/
  fitness.py`, and the battery alias splits in two;
* `books crop` was specified as two different crop paths (feed's and
  read's): it is read's driver with a transport that answers nothing, and
  `feed.py` is deleted except one geometry helper;
* the label examples contradicted the tree's fingerprints (`paddleocr-vl` is
  the reader name, the model is `PaddleOCR-VL-1.6-0.9B`): every adapter
  declares `label()`, and identity is defined with `VLM_SEED` and without
  run-born keys;
* `consistency` refusing two runs of one identity refused the very
  measurement it cited: the identity includes the seed, and the measurement
  is three runs at three seeds;
* dots page sets have no `run.json` and would be unmeasurable under `Run`:
  the migration writes one with `builder: absent`;
* `UnknownLabel` is "could not count", not a refusal;
* `bench all` had no output flag and `bench accept` cannot be scoped to one
  bench; `bench/expected` and `bench/results` are not books;
* `doctor` imports `remote` and was outside the rule;
* `bench/real` has no truth and a page selector; `bench/*/html` and `check/`
  were unmentioned;
* the `__file__` checklist missed `config.py` (the worst: one level deeper
  and every secret reads as unset), `schema.py`, `acceptance.py`, the
  `sha256_crop_code` sibling hash in `html.py`, the `run.py` self-hash, and
  the MathJax directory that must travel; `html.py` writes its module name
  as a literal; `replay` identifies the writer by module string, so the
  three tracked snapshots need a rename table;
* the migration table must map symbols, not modules, for the five split
  modules, and mutation targets follow the symbols.
