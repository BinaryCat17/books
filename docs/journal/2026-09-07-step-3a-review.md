# 2026-09-07: the skeptic on step 3a, and what each objection became

Fifteen findings against the two 3a commits. Thirteen adopted, two adopted
with a different fix than proposed, none refuted. The package move itself
(`c362a00`) came through clean: no upward import, every root computation
right, `replay.RENAMED` covering exactly the three writer names that appear
in tracked snapshots and no invented one. Its debt was prose, and the
migration script could not have paid it -- it rewrites string constants
whose WHOLE value is a moved path, and a comment is not a constant.

## The two that broke the commit's own claim

**The crops are something a paid run believes.** `read_with.json`, `pages/`
and `answers/` were guarded; the crops were not, and they are the point.
`answers/*.json` records `observed.crop` -- file, dpi, width, height,
clipped by the sheet -- describing those very files, and they are the only
surviving picture of what the money bought. So `books crop --out <a read
directory>` overwrote them at whatever `CROP_MARGIN` was in force, exit 0,
no warning, while `answers/` went on describing the files that were sent.
Proved by the reviewer with two runs at different margins: different bytes
under the same names. `books html` refuses this class of accident by asking
whether a directory is its own; the preview now refuses on four tells
(`answers`, `pages`, `read_with.json`, `run.json`), before cutting
anything, and a check confirms the paid crops are untouched after the
refusal.

**`would_ask.json` reported a resolution nothing was cut at.** The preview
wrote the RULE's float under `crop_dpi`; the paid run writes the dpi it was
CUT at under that name and the rule's under `crop_dpi_by_rule`, and the
comment forty lines away says why: `crop.cut` renders at `int(dpi)`, and
the two disagreed on 328 boxes of 379. On `bench/real/tables20.pdf` the
preview said 588.911 where 588 was cut. The tests could not see it: the
fixture page is vector, `native_dpi` is None, both boxes are
`below_model_min`, so the rule returns exactly `PAGE_DPI` and rule and deed
coincide. A second fixture now carries a 2000x2000 raster on a 200x200 pt
sheet, one box over nearly the whole page: the rule answers 379.61 and the
crop is cut at 379. The check compares the preview's three dpi keys against
the paid run's `observed`, key for key.

## Our knob, charged to the model

`raster.cut` called `params()` unconditionally, and `params` validates
`CROP_DPI` -- so on the two paths that name each crop's resolution
themselves and never use the knob, `CROP_DPI=0` or `nan` raised a
`ValueError` the driver files as `crop_failed` and `report()` prints as
"THE CROP FAILED ... the model's box is degenerate or lies off the sheet.
That is its defect, not ours." Under a registry line, rewritten in that very
commit, saying the path does not read the knob. The fix is not to correct
the line: `cut` now asks for the margin alone when the caller names the dpi
(`want_dpi=False`), so the registry line is true. The margin is a different
matter -- the reading path does apply it -- and is still read.

## A check that reintroduced the hole it was written to close

Both directions of the map check, and both of the new header check, asked
`f"books {c}" not in text`. Justified by "a prefix counts: `books bench all`
names `books bench` too" -- but it counts every other prefix as well. The
reviewer added `sub.add_parser("doc")` to a copy of `cli.py`, named it in
neither list, and all three "names all" checks passed: `books doc` is inside
`books doctor`. `app`/`apply`, `syn`/`synth`, `sub`/`subset`,
`over`/`overlay` are the same shape. The names are parsed out now, and the
only prefix rule left is the real one: a group is offered by the line that
offers one of its subcommands.

## Dead code with prose about deleted behaviour

`_union_rects` came over from the preview with `_union_area` and nothing
read it -- one grep hit, its own definition -- while its docstring went on
explaining how the number of holes chooses between `crop` and `masked_page`,
and two journals called the builder "its last reader". Deleted; its
measurement is in the preview journal with the rest.

## The preview as an instrument

Three findings say the same thing: it showed less than it knew. It listed
only the questions, so a run where every crop failed wrote `"asks": []` and
nothing else -- no anchor, no reason, exit 0. `would_ask.json` now carries
`not_asked` and `crop_failed` beside `asks`, the command prints the crop
failures and says out loud when not one block would be asked, and `books
crop` takes `--policy` exactly as `books read` does (without it,
`bench/annopage/detect` -- a run `books read --policy PP-DocLayoutV2` reads
perfectly well -- could not be previewed at all). And `preview` with
`resume` is refused rather than quietly ignored: the answers a resume would
reuse live in the read directory, where a preview may not write, so a
preview shows a FRESH run and says so.

## Prose, in bulk

About forty pointers in `src/` to files the move deleted. Four reached a
user or a file: two `Refusal` messages, a log line, and one string written
into `run.json` as `why_removed_by_label_empty` ("see pipe_meta in
models/docling_heron.py"). The rest were docstrings and comments across
fifteen modules, six checks and five documents, `CLAUDE.md` among them --
its "prose beside its code" paragraph itself sent the reader to
`doc/html.py`. All now name what exists. The one old name left in `src/` is
in `replay.RENAMED`, where it is the data.

Two smaller ones: the `UNPLACED` comment described a permission no module
may use (`test_nothing_imports_the_command_line` bans importing `cli` from
anywhere), and a mutator's docstring still spoke of `doc/feed` and
`feed.json`.

## And one the reviewer found while I was not looking for it

`.gitignore` still hid `bench/*/detect/feed/` and `bench/*/feed/` -- both
written by the deleted command -- while what `books crop` writes,
`<detect dir>.crop/`, was hidden by nothing on annopage, annopage-lite,
hard and hard36. (On the six synthetic benches the whole directory is
closed, so it was hidden by accident.) The patterns now name the crop
directories, and `test_the_things_that_must_never_be_committed_are_ignored`
asks git about two of them.

## What guards all of it

Five new mutations, all caught: the preview reporting the rule's number as
the dpi it cut at; a preview landing on a paid read directory; the preview
keeping the questions and dropping the reasons; a preview resuming;
`CROP_DPI` validated on the paths that never use it. Battery 311 of 311
caught, 0 uncaught, 333 of 362 checks under a mutation.

Fast suite 362: passed 361, skipped 1. Anchors 81 land. Ratchet holds.
Import rule 0 violations.
