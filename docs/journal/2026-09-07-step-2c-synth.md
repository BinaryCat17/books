# 2026-09-07: step 2c, the generator as a package, proved by identity

`synth.py` was 2 002 lines and five concerns: the drawers and the
character-truth channel, the handbook's forty cases, the aging, the
measured truth, and the build. It is a package now, cut by section:

| file | lines | holds |
|---|---|---|
| `synth/draw.py` | the drawers, `_say`, the RU/EN text constants, the handbook sheet constants that `_page` and `_flow` default to |
| `synth/books/spravochnik.py` | the handbook's cases, CASES, ROTATE, SPREADS, SHEET, ABOUT: a book module like the other five at last, loaded by name like them |
| `synth/age.py` | AGING, the aging, the binding shadow, the three box transforms |
| `synth/truth.py` | INK, KEEP, GUESSED, GROW, the ink measurement of boxes, the text-layer check |
| `synth/__init__.py` | build and the module docstring; re-exports INK, AGING, SynthError for the two tests and the command that ask the package |

The dependency graph of the cut, computed by ast before cutting: the
drawers need nothing from the rest; aging and truth need only the error
class; the handbook needs the drawers; the build needs all three. No
cycle, and the `books` package moved under `synth`, which ends the one
cycle the audit found (`synth` importing `books` lazily while every book
imported `synth`).

The manifest's `generator` field records the package: four files hashed
by their own `__file__`, and the book module a fifth.

## The proof

All six books were built with the generator BEFORE the cut into a scratch
directory (seed 1, aging old, as their tracked manifests say), and again
AFTER it: 85 files of the five other books (80 truth pages and five PDFs)
byte-identical; slovar's 13 truth files identical to the tracked lock and
its PDF the same hash. The split changed no pixel and no box.

The ratchet exempts book prose by the `_RU` suffix of the constant's name,
not by file, so the constants' move to `draw.py` did not disturb it.

## Second half: the truth says its order is known

The synthetic truth wrote `order` on every block and never `order_marked`,
so the one bench where reading order is exact printed NOT SAID on every
page and the metric could not score it. The generator writes
`order_marked: true` now: the drawers append blocks in the order a reader
takes them, and that index is the order. A case that draws out of reading
order is a truth defect for the eyes.

The six benches were rebuilt in place (seed 1, aging old). What moved:

* the truth files' `meta` (one key), and so the tracked lock of slovar's
  truth hashes;
* the six tracked manifests: the generator recorded as a package of four
  hashed files plus the book module, the commit marker in the writers'
  shared form, and the knob descriptions in English at last (they were the
  Russian of the build that made them, a record the ratchet exempted);
* the two records taken against slovar said INPUTS MOVED, the manifest and
  the truth, and "the result is the same to the last key" -- the shape the
  step-0 review asked for, on its first real use;
* the contour battery on slovar measures 30 probes of 33 instead of 26:
  the three order probes and the erased-flag probe have something to
  measure with;
* the table on slovar: model order 0.886 and assembly order 0.886 over 13
  of 13 pages, where both were absent with a footnote.

That last number is the first measurement of reading order against a
truth that knows it. On the handbook, the dictionary and the four others
the same figure is one `books bench all` away. `bench/hard`, the distillate,
still carries the synthetic pages' old meta (NOT SAID on its six synthetic
pages): it is tracked, and the plan's 3b rebuilds it when its manifest gains
`derived_from`.
