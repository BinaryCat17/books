# 2026-09-07: step 2a, second half -- the moves into datasets and the ink split

The measurement bodies left the root. `tools/migrate_layout.py --step 2`
carried them (44 import statements in 32 files, 29 literal strings, 7
attribute uses through an alias, 9 moves, the `books` package as one) and
the merges were done by hand: the wrapper classes step 2a wrote joined the
moved metric files, and `fitness.py` split into `processing/assess/ink.py`
(the measurement: `measure`, `report`, the thresholds, the ink cache) and
`datasets/metrics/fitness.py` (the battery and the `Metric`). The battery's
threshold closure `_at` now sets the threshold ON THE MEASUREMENT MODULE,
where `measure` reads it, and the battery names every threshold as
`ink.X`; the first run after the split threw NameError on two probes, which
the fitness-selfcheck lock caught.

The page loader moved once more, from `datasets/bench.py` to
`core/page.py`: the ink measurement in `processing` reads pages too, and
processing may not import datasets. `tree/imports.py`'s `UNPLACED` shrank to
the six names step 3 places (`detect`, `djvu`, `models`, `doc`, `read`,
`cli`); the rule is enforced on everything else and reports zero.

## What the string pass got wrong, and the fix

The migration's literal-string rewrite mapped every old path to its new
one, and the `books` package's directory name is also the command's name.
Five `"books"` literals became `"datasets/make/books"`: the argparse `prog`,
the three `repeat_command` argv lists, and the `UNPLACED` tuple. The help
snapshot caught the first within a minute (`usage: datasets/make/books`).
The synthetic generator's self-hash was built beside its own file by the
sibling's name and that name was rewritten too; it hashes `__file__` now.
The script no longer rewrites a package's bare directory name, only `.py`
paths and repository paths.

## What the instruments said

Fast suite 343, acceptance nine reports and four records same (the record
table points at the moved modules), anchors 72, attrs 216, ratchet 1105,
import rule 0 violations, slovar rebuilt with the moved generator: 13 of 13
truth files and the PDF byte-identical. The manifest's `generator.file` now
reads `datasets/make/synth.py` and its commit the current one, as the plan
said it would.

## The 2a review, and what it found

Five defects, fixed in the commit after the moves:

* the import exemption faced the wrong way: `UNPLACED` exempted the
  IMPORTED side for everyone, so `core` importing `doc.html` passed. Only
  `datasets`, `processing` and `cli` may reach an unplaced body now, and a
  planted `core -> doc` import is named;
* `Scalar.over` meant three things in one column (the fraction behind a
  share, a coverage in pages, a coverage in blocks) and named none. A
  scalar carries `count` (numerator, denominator) apart from `over`
  (counted, of) with a `unit`, and coverage without a unit is refused;
* `CER_artefacts` repeated the coverage bug the commit claimed to fix for
  `CER`; it is over every artefact block now, with the answered-only figure
  its own line;
* `--only` crashed on a typo, bypassed applicability, and wrote a partial
  table over the full one's file. It refuses an unknown name and an
  inapplicable metric, and names its own file;
* the table had no test and no lock. `tests/test_table.py` checks the
  refusals, the single parse, the read-back and the rendering on a made-up
  bench; the acceptance report `table-slovar` locks the real text.

Weaknesses taken: the truth is parsed once per table and the metrics take
the dicts (`Metric.run_loaded`); the two private loaders delegate to
`core.page.load_pages` under their own error class, and the contour
metric's identity check delegates to `bench.same_book`, whose wording for a
bench without a manifest now matches the old check's; the ink wrapper adds
"cut as one picture" and says which shares the report divides and which it
counts; the docs-map test sees an unassigned `add_parser`; a whitespace
line the move left is gone. The step-1-reviewed commit's message said
"checks 343" for a tree at 329 and "nine imports gone" for six; the record
stands corrected here.

Still owed from the plan's 2a, for 2b: `snapshot.py` and `assembly.py` as
metrics, `mutate.py` and the fold of the three batteries onto
`run_battery`, the overlay's own identity check, and the six loaders
reduced to one call site each.
