# 2026-09-07: what in this tree is not pipeline code, and what of it went

Asked directly: is there unnecessary code, unnecessary measurement files,
documentation nobody needs -- and what is `src/booksmith/tree/` doing there
at all. Answered by counting rather than by taste, and acted on where the
count was unambiguous.

## Dead code: three names in 25 597 lines

Every module-level `def`/`class` in `src/`, against every reference in
`src/`, `tests/` and `tools/`. Three names are referenced nowhere, their own
file included:

* `datasets/bench.py:vocabulary_of` -- deleted (with the `policy` import it
  was the only user of).
* `tree/cyr.py:latin_areas` -- deleted.
* `metrics/contour.py:cover_many` -- KEPT, and the strike refuted for the
  second time. It carries its own note: struck out as dead once, a sceptic
  reversed the strike, and the reason is that `sense()` covers one box at a
  time, so a half-and-half split lands in "cropped" though the union covers
  the object whole. Wiring it in MOVES a golden-bench column ("cropped 85"),
  which is a change of metric to measure and explain, not a tidy-up.

Three in twenty-five thousand lines is a clean tree by this measure. The
waste is elsewhere.

## A package that was nothing but a name

`src/booksmith/run/` held one empty tracked `__init__.py` -- the shell of the
package whose contents became `core/` in step 1. It shipped to the rented
card with the rest and appeared in no map. Deleted.

## Three tools of a finished job

`tools/migrate_code.py`, `tools/migrate_keys.py`, `tools/keymap_check.py`
and the two maps only they read (`valuemap.json`, `htmlmap.json`). The job
is provably finished: zero Cyrillic KEYS in the 6041 json files of `bench/`,
`processed/` and `runs/`. What the three knew -- the round-trip proof before
rewriting, the five ways a key map destroys data silently, the five
syntactic positions a key takes in code, and what must never be rewritten
(the append-only rent journal, the model's answer, the swap journal whose
sha256 would have to be forged) -- is in
`docs/lessons-from-deleted-code.md`, which exists for exactly this. The map
itself stays: `tests/test_data_contract.py` looks a pre-migration spelling up
in `keymap.json` rather than typing one, so the record is READ and cannot go
stale.

Deleting them cut the Cyrillic residue from 1105 characters in 21 files to
926 in 18 -- sixteen per cent, at no translation cost, because their subject
was Russian and the lock said so ("TOOL: the migration's own subject").

## `src/booksmith/tree/` -- the question was fair

It is not pipeline code and never was: nothing in it opens a PDF. It is
three instruments over the source tree, and they are inside the package for
one reason -- the mutation battery has to be able to damage an instrument
and watch a check go red, and a patch applied to a `tools/` script never
reaches a check that imports the module. `tools/cyr.py` is nine lines around
`booksmith.tree.cyr`, and `tools/acceptance.py` is the same shape for the
same reason.

What each one is: `imports.py` enforces the three-layer rule this whole
refactor rests on; `cyr.py` is the ratchet that stops the translation
sliding back, plus the residue lock that says what is left and why;
`figures.py` is new (below). Each makes a rule CLAUDE.md states countable,
and a rule stated but not counted is precisely the disease that file opens
with. They stay -- but the map now says out loud that they are not pipeline
code, which it did not.

The one real cost is that they ride to a rented GPU inside the package. It
is not worth fixing: 84 KB of instruments against 2.2 GB of weights, and the
package travels whole ON PURPOSE -- the one place that retyped code instead
of shipping the package diverged from it on four inputs of thirteen.

## The documents restate each other, and now it is a number

`CLAUDE.md` opens with the disease -- one figure standing in six places at
once -- and the rule was guarded in exactly one place: four named numbers
forbidden to return to the map. Between the documents themselves nothing
counted at all.

`booksmith.tree.figures` counts it. A measurement is four significant
digits, a money amount, or a percentage to a decimal; three-digit numbers
collide by chance and an instrument that cries wolf gets switched off
(measured: a three-digit bar finds 114 "duplicates", a four-digit one 29, of
which a year and a graphics card are declared not measurements). Journals
are not read: a journal entry is a dated record, like the rent ledger, and
its numbers are what was true that day.

Twenty-five measurements stand in two documents or more. The heaviest pair
is `docs/contour-notes.md` against `docs/models.md` -- fourteen figures
stated twice, among them four percentages and the artifact counts. Second is
`docs/limits.md` against `docs/models.md`: five, including all three sums of
money this project has spent. The ceiling may fall and never rise, and a
fall that leaves the ceiling behind is red too, or the number stops
pressing. Step 5 of the plan is the documentation split; this is the number
it has to move, and it is now the first thing that will say whether the
split worked.

Two mutations hold it: a duplicate that stops being counted, and the
four-digit bar dropped to three so the instrument cries wolf.

## What was looked at and left alone

* `docs/contour-notes.md` (1036 lines) is the largest document and the
  worst duplicator -- but it is not redundant with `docs/models.md`: one
  says how a number was obtained and what the traps cost, the other what a
  model is and what it found. The overlap is the numbers themselves, which
  is what the count above is for.
* `tools/spread_probe.py` looks like a one-off measurement script and is
  not: `tests/test_djvu.py` imports and runs it, so the veto's claim can
  fail. `tools/prose_only.py` is dead today and folds into a command in
  step 3c.
* `bench/results/slovar-detect.json` is `books bench all` output, ignored by
  git, regenerated by re-running it.
* The disk hogs are all untracked and all regenerable by eye: 2.8 GB of
  drawn overlays under `bench/annopage/check/`, 162 MB under `bench/hard36`,
  93 MB of stale `bench/*/html/` builds that step 3b deletes. Nothing to
  decide there; `books overlay` draws them again in minutes.
