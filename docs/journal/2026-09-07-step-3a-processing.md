# 2026-09-07: step 3a, first half -- module 1 under `processing`, names unchanged

`tools/migrate_layout.py --step 4` moved the detector, the adapters, the
reading contract with its transport and driver, the two rented jobs, the
builder with the swap layer, and the djvu unfolding under `processing/`:
87 import statements in 34 files, 64 literals, 12 moves, two packages whole
and three modules renamed on the way (`read/http.py` is
`transports/openai_http.py` because it is the OpenAI-shaped delivery and a
second shape is coming; `read/run.py` is `driver.py`; the reader left the
rented job's package for `readers/`). By hand: the MathJax directory
travelled with the builder; the docker image constants went to
`remote/image.py`, so the layout job no longer imports the reading job for
the name of an image; the rented job finds the package it ships from
`booksmith.__file__`, never by counting levels (two levels deeper, two
`dirname`s would have shipped `processing/read` as the package, learnt on a
rented card); the driver hashes itself by its own `__file__`; `Recognizer`
is `Detector`, 29 places; `models/` is gone and the exemption list holds
`doc` (the preview, until the second half) and `cli`.

The tracked snapshots name their writer by the module path it had: the
checker's `RENAMED` table translates, the snapshot stays data, and the
report on the golden bench says "processing/layout/adapters/doclayout.py
is not the code that counted" where it said `models/doclayout.py`. That is
the one acceptance line that moved, and it was regenerated with this
reason.

## What went wrong on the way

The package move landed one level too deep (`processing/read/read/`)
because the target directory existed; repaired by hand. Relative imports
in moved files were left relative when their TARGET had not moved, and a
file two levels deeper resolved `from ...remote.spec` to a package that is
not there; the script re-emits every relative import of a file that moves
now, and the three that had slipped were rewritten against the files' old
names. Six tests built old paths from components the string pass cannot
see; fixed by hand, as the plan said they would be.

## What the instruments said

Fast suite 352, mutation anchors 73 and attrs 223 resolve, acceptance ten
reports and four records same after the one regeneration, ratchet 1105 in
21 files, import rule 0 violations with `processing` now a real package.
