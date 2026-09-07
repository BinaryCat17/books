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

(The numbers for the step as a whole are at the end.)

## Second half: the preview is the driver, and three knobs go

`books feed` cut the pages with three knobs of its own (`VLM_INPUT`,
`MASK_FILL`, `FEED_DPI`) that `books read` never read, at a dpi of its own,
and showed pictures the paid path never sent. `books crop` is the read
driver in preview: the same crop rule, the same dpi, the same prompts and
generation parameters, written to `crops/` and `would_ask.json`, nothing
sent. On two pages of slovar it cut 93 crops and listed 93 questions (42 and
51), each with its anchor, label, prompt, kind, crop dpi and the reason for
it, plus the crop's width, height and whether the sheet edge bit it.

Two things the first attempt got wrong, and both are the same mistake --
preview borrowing the paid path's bookkeeping. The driver built
`read_with.json` before the page loop, so the preview called
`fingerprint()` on a transport it does not have and died on `None`; and it
made `pages/` and `answers/` for a run that fills neither. Both are now
behind `if not preview`, and the first is not merely a guard: a preview
that wrote `read_with.json` would be believed by the next paid `books read`
resuming into that directory, which would compare against a setup no money
ever bought.

`doc/feed.py` and the three knobs are gone; what the module and the
registry had measured stands verbatim in
`docs/journal/2026-09-07-preview-knobs.md`. Of the two hole-geometry helpers
the preview wrote, `_union_area` moved into the builder, its last reader;
`_union_rects` moved with it and nothing read it -- it counted holes to
choose between `crop` and `masked_page`, a choice that went with the knob --
and it is deleted, its measurement kept beside the rest of the preview. The registry counts
36 knobs, 34 with readers, 2 debts; "eight empty defaults" became seven and
says why. The snapshot report on the golden bench and the table on slovar
moved by the three keys the registry lost, and were regenerated with that
reason; `help` gained `crop` and lost `feed`. `models/` and `doc/` are gone
and the exemption list holds `cli` alone.

## The 2b and 2c review, folded in here

Two defects. One synthetic magazine page (`zh_side_caption`) drew its side
caption before the right column and the left column's tail last, so the
truth's order, now marked and scored, was not a reader's: eighteen wrong
pairs on one page, found by a reviewer's heuristic over all 93 synthetic
pages, not by a probe. The case draws in reading order now and zhurnal was
rebuilt; its PDF hash moved with the content stream while the pixels
stayed. The other: `--selfcheck` through `Bench.open` refused any truth
directory not laid out as a bench, where the same two arguments without
`--selfcheck` measured fine. `Bench.bare` takes such a directory, says the
identity is NOT CHECKED, and the ink battery takes the PDF given by hand.

Taken as well: the order metric scores every matched block, furniture and
artefacts included, and the generator places those by the book's habit;
the convention is written beside `order_marked` in the generator so that a
disagreement on those pairs reads as what it is. The 2c-ii journal
understated the manifest change: four knobs new since the last build and
two `set_externally` flags flipped by the rebuild's environment moved too.
Stale lines in `stamp.py`, the reading metric's message, two tests and the
plan were corrected.

## A header that claimed to be checked, and was not

`cli.py` opens with the command list `books --help` prints, and it said of
itself "THE LIST IS CHECKED AGAINST `sub.add_parser`". Nothing checked it:
`tests/test_docs_map.py` checks `CLAUDE.md`, both directions, and had never
looked at this list at all. So it went on offering `books feed` after the
command was deleted, and had never heard of `books bench all` -- the
one-table command, missing from the header since it was written. The check
now covers the header too, both ways, over the indented `books ...` lines
only: the prose below them names deleted commands on purpose, and that is a
record, not an offer. Proved both directions fall -- drop the `crop` line
and it names `crop` missing; add a `feed` line and it names `feed` a ghost.

Five more places still spoke of `books feed`: the knob registry twice (the
`CROP_DPI` text, which rides into every `run.json`, and the docling
measurement), the synthetic generator twice, and the run-directory helper's
worked example. All now name what exists. Where the three deleted knobs
stood, the registry says what they were, who read them, and where the
measurement went.

## What guards the preview

Three mutations, all caught: the preview cutting at a resolution of its own
(as `books feed` did), the preview writing `read_with.json`, the preview
making `pages/` and `answers/`. Two checks stand under them -- the crops of
a preview and of a paid run compared sha256 by sha256 on the same tiny
book, and the list of what the preview left behind.

One thing the fixture cannot say: its page is vector, so the rule's answer
IS the page dpi there, and a mutation setting the preview's dpi to
`PAGE_DPI` would move nothing. The mutation doubles the number instead, and
the reason is written beside it -- otherwise the next reader takes a
green battery for a statement about `PAGE_DPI`.

Two more mutations went in beside them for the header check, and one for
`bench/expected/slovar-truth.sha256` -- the step-0 lock over the 13
synthetic truth files, which until now was read by `sha256sum -c` typed by
hand and by nothing else. It is a check in the suite now, skipping with a
reason when the untracked bench is not built, and a mutation moves the
truth out from under it (by symlinking the bench and doctoring a COPY of
the lock: the battery does not touch the tree).

## The numbers at the end of step 3a

Fast suite 357: passed 356, skipped 1. Mutation battery 306 of 306 caught,
0 uncaught; checks under a mutation 328 of 357 (the commit message says 327
-- I quoted a run taken before the last mutation went in; every other number
in it reproduces). Anchors 76 land, attrs 225 of which 223 resolve.
Acceptance: ten reports and four records same -- `help` regenerated for
`crop`, `text-slovar` and `fitness-slovar` re-taken after the bench rebuild
said INPUTS MOVED with the result the same to the last key. Ratchet 1105
Cyrillic in 21 files, no area grew. Import rule 0 violations. Registry 36
knobs, 34 with readers, 2 debts.

All six synthetic books were rebuilt from the edited generator, so their
manifests describe the code that is committed. The slovar truth came back
byte-identical, all 13 files against the lock.