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
