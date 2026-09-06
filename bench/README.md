# bench/ -- the benches

```
bench/
  annopage/       THE GOLDEN BENCH: 600 real pages, truth by librarians
                  (AnnoPage, Zenodo 10.5281/zenodo.12788419, CC BY 4.0). Only
                  non-text categories are marked up -- 1232 artefacts and not
                  one text block; reading order not marked up at all
  annopage-lite/  the same 600 pages squeezed to 1 Mpixel: what dots.ocr sees
                  inside itself, truth rescaled by the same factor
  hard/           the squeeze of both benches: 130 pages where two artefacts of
                  one label stand side by side (124 of them real)
  hard36/         the 36 hardest of those
  real/           three PDFs of our own scans. NOT marked up by hand -- the one
                  thing the bench still lacks
  expected/       acceptance snapshots: seven command reports, compared as text
                  by `tests/test_acceptance.py`
  spravochnik/    \
  slovar/          |  six synthetic books with EXACT truth, characters and
  matematika/      |  table grids included. Not versioned: one command rebuilds
  atlas/           |  them byte for byte -- seed, aging profile and the sha256
  katalog/         |  of the generator are written into manifest.json
  zhurnal/        /
```

Every book directory is built alike:

```
bench/slovar/
  slovar.pdf      the book itself
  truth/          truth by page, measured by ink; a text block carries its
                  CHARACTERS, a table its rows, columns and the text of every
                  cell (artefact truth sits beside the page, by block number)
  check.pdf       ONE sheet-with-boxes file -- what has to be looked at with
                  eyes; not versioned, drawn by books overlay
  detect/         the model's output plus the full input snapshot
  html/book.html  the product of the first level: what the book turns into
  manifest.json   what this truth was built with
```

`bench/annopage/` is the exception and the only one: there `check/` is a
DIRECTORY with one file per detector -- `PP-DocLayoutV2.pdf`, `V3`, `plus-L`,
`YOLOX-layout`, `docling-heron`, `docling-egret`, 496 to 498 MB each. Both are
kept out of git by name: `bench/*/check/` for the directory, `bench/*/*.pdf`
for the single sheet.

**What is versioned and what is not.** One rule, written in `.gitignore`: git
carries what cannot be rebuilt for free -- truth, `manifest.json`, the input
snapshot `detect/run.json`, and output paid for on a rented card. The books
themselves (472 MB for annopage), the boxes, the sheets and the assembled
product do not travel; the CPU makes them from one command.

## Three instruments, and the input each of them is honest on

**The bench has three instruments**, each with its own corruption battery:
`books score` -- contours and labels; `books fitness` -- fitness by INK, no
truth needed; `books text` -- characters and table cells. (`tests/run.py
--selfcheck` is a fourth battery but not a fourth instrument: it measures the
conspiracies between files, not the bench.) Measuring with one alone is a
mistake already paid for: `books fitness` by construction does not penalise the
merging of neighbouring boxes, and judging the docling pipeline by ink alone
priced it at seven objects instead of a hundred and thirty-two.

**"Zero uncaught" is a property of the INPUT, not of the battery.** `README.md`
tabulates which battery is green where; the reasons are properties of these
benches, measured 2026-09-06:

| what the bench is | what the battery does |
|---|---|
| the truth carries characters, `detect/pages` does not (`slovar` page 0003: 75 detected blocks, 0 with `content`, against 60 of 60 in the truth) | `books text` is zero only on `<book>/truth <book>/truth` -- 0 uncaught, 18-19 of 29 probes measured; against `detect/pages` it returns 1 with 2 to 5 uncaught, "answer shifted by a page" and "every tenth character dropped from the truth" having nothing to break |
| annopage marks up non-text objects only | the same battery prints **uncaught 3** there, 20 of 29 probes unable to measure anything |
| `slovar`, `matematika` and `zhurnal` print "solid dark columns 0 on 0 pages, scanned without a gutter shadow" | `books fitness --selfcheck` reds on exactly those three: the probe blows `GUTTER` to 0.0, squeezes it to 1.0 and demands the count fall below a base of zero. The other three books: 21 probes, 0 uncaught |
| `models/doclayout.py` is no longer the code the snapshots were taken with (snapshot `c7506498`, tree `298a2d54`) | `books replay --selfcheck` returns 1 on all seven benches while uncaught losses are 0 on every one: 26 fingerprint values unverified, 4 keys absent from the start, 17 on annopage. Stale, not incomplete |
| one page is not a book | `books score` is 0 uncaught on all six books and on annopage, 33 probes, and false-fails on a ONE-PAGE directory: 2 probes on a dense page (page shift, `TOUCH=1.01`), 10 on a sparse one |

**Truth against itself is the one input where reading has a known answer**,
which is why the acceptance snapshot uses it. In four of those five the red is
at least in part **"nothing to break" reported as "did not catch"** -- no probe
carries a guard of its own applicability. The numbers are still worth reading;
it is the guard that is missing.

## The real pages the old pipeline broke on

Three PDFs in `bench/real/`, scans of one machine-tool reconditioning handbook:
dense two-column setting, tables **without a single rule**, columns held
together by spaces, in places a faded impression.

| file | what it is |
|---|---|
| `tables20.pdf` | pages 302..321 of the book -- the ones the tables were measured on |
| `holdout20.pdf` | the held-out sample, pages listed in `holdout20.pages.json`: 4, 40, 143, 292, 393..400, 443..450; fourteen of the twenty have no tables at all, for false positives |
| `test25.pdf` | twenty-five pages from the start of the book |

**The parses were deleted, and not by oversight.** `mistral/` and `olmocr/`
lay here -- two models' output serving as a "reference". It was not one: it is
a second reading, its errors are documented (p. 311 "Pool Room Lathes", p. 314
`(1)`/`(2)` instead of `(±)`), and the metric took its denominator from it, so
it could not see anything both systems missed at once. Deleted so they cannot
be raised as truth again.

**What these pages are worth now.** The golden bench is somebody else's scans,
and the synthetic one gives exact truth but no fifties letterpress on yellowed
paper -- exactly where `Laths` is read for `Lathes` and `mch` for `inch`. So
these pages go into a hand-marked golden bench. Known to be hard, from the old
parses: 304 (third column unreadable, the model completed it from the pattern),
313 (a box across the gutter), 317 (one column taken of three), 40 (a table
labelled `display_formula`), 4 (a contents page with dot leaders).

---

## The synthetic bench: six books

Not versioned (10 to 62 MB per book), rebuilt by one command byte for byte the
same -- seed, aging profile, generator sha256 and commit go into
`manifest.json`:

```
books synth   --book slovar --out bench/slovar
books detect  bench/slovar/slovar.pdf --out bench/slovar/detect
books score   bench/slovar/truth bench/slovar/detect/pages
books score   bench/slovar/truth bench/slovar/detect/pages --selfcheck
books overlay bench/slovar/slovar.pdf --truth bench/slovar/truth \
      --detect bench/slovar/detect/pages --out bench/slovar/check.pdf
books html    bench/slovar/detect --out bench/slovar/html
```

| book | sheet | pages | what it checks |
|---|---|---|---|
| `spravochnik` | 506x733 pt | 36 | tables of every size, spreads, rotations, drawings |
| `slovar` | 340x578 | 13 | narrow columns of prose: is merging a property of the table or of proximity |
| `matematika` | 468x662 | 12 | `display_formula` against `table`: matrices, fractions, formula numbers |
| `atlas` | 720x506 | 11 | the drawing field, the title block, a specification inside a drawing |
| `katalog` | 506x733 | 11 | a strip with no prose, a table continuation, a footnote under a table |
| `zhurnal` | 540x760 | 10 | a boxed insert, a side caption, an abstract, a reference list |

`check.pdf` shows **DISCREPANCIES**, not everything: **thin grey, unlabelled**
means truth and model agree, and there is nothing to look at; **thick red, "НЕ
НАШЛА"** is in the truth with no pair in the model; **orange dashes,
"ЛИШНЯЯ"** is in the model with no pair in the truth.

On a good page the sheet is almost blank; on a bad one you see exactly the
trouble. The first edition drew both markups in full -- two hundred nearly
coincident boxes, two labels over each -- and the sheet stopped being readable
exactly where there was nothing to read. Nor were the dashes drawn: `dashes`
was passed as a tuple where pymupdf wants a string, so it silently drew a solid
line and the two markups were indistinguishable.

**Looking is mandatory, and that is paid for six times over.** Not once did the
number look ill while the bench was lying: empty text boxes (`insert_textbox`
draws nothing when the text does not fit and quietly returns a negative); the
right half of a spread off the edge of the sheet (pixels in a field counted in
points); a "drawing" made of forty-seven parallel lines; a formula box 83
points wider than the formula; one box for a running head that the model
correctly gives as two; a line as a truth block where only a paragraph is ever
a block. Hence the three rules of the bench:

* truth boxes are **measured by ink** (`_measure`), not declared by a number;
* an empty box **fails the build**, rather than handing the model an eternal
  undeserved miss;
* a box grows **only along solid ink** -- a gap means what follows is no longer
  ours.

### Aging profiles

| profile | what it adds |
|---|---|
| `clean` | nothing: clean typography |
| `scan` | light blur, grain, tint, 0.5 deg skew, JPEG 85 |
| `old` | the same, stronger: 1.2 deg skew, JPEG 68 -- **the default** |
| `decayed` | + show-through from the back and a dark scan edge, twice the specks, JPEG 52 |

The profile is set by the knob `SYNTH_AGING` and **gets no directory of its
own**: `SYNTH_AGING=decayed books synth --book spravochnik --out bench/decayed`
builds the same book on decayed paper when there is something to compare.
Keeping such a copy around is pointless -- a minute to make, and it gets
confused with the books in the listing.

Aging is not decoration: on a CLEAN page there is no `table` box at all, while
on an aged one it appears together with a competing `text` box on the very same
rectangle.

**The skew of `old` and `decayed` is DELIBERATELY identical.** Skew is the only
part of aging that moves truth boxes (the affine matrix carries them through
`_xform_box`), and its angle comes from a separate generator so as not to
depend on the number of specks. At equal skew the two profiles' truth boxes
match byte for byte on all 36 pages, so a difference in the number belongs to
the paper and not to truth that slid. The previous edition gave the decayed
profile 1.8 deg while promising in this same file that boxes do not move -- all
382 moved, by up to 28 pixels.

### What the bench does NOT give

Fifties letterpress on yellowed paper -- the kind where `Laths` is read for
`Lathes`. This bench is about GEOMETRY and LABELS, not about reading
characters. Colour, either: `_age` converts the page to grey, so the channel
order at the model's input goes unchecked here in any way. Nor curvature of the
sheet at the spine -- it is not expressible as an affine transform, truth boxes
after it would have to be computed approximately, and approximate truth is
worse than none.
