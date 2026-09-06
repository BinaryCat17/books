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
