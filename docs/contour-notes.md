# What has been measured on level-one contours

Everything here was measured by `books score` against the synthetic bench
books, whose truth is MEASURED BY INK, and reproduces with three commands:

```
books synth  --book <book> --out bench/<book>
books detect bench/<book>/<book>.pdf --out bench/<book>/detect
books score  bench/<book>/truth bench/<book>/detect/pages
```

Six books, **93 pages, 1321 truth blocks** — 1211 of them text and service,
110 artifacts on top of that. The model is `PP-DocLayoutV2`, ONNX on the CPU.
**The threshold is the weights' native 0.5** (`draw_threshold` from
`inference.yml`); the knobs `LAYOUT_SCORE_THRESHOLD` and
`LAYOUT_TABLE_THRESHOLD` stand at the same value. The metric passes a battery
of **thirty-three probes** on every book (`books score … --selfcheck`), 0
uncaught on our own V2 layouts — seven of them when this line was first
written, nine by the audit of section 14.

| book | pages | artifacts | found | text and service |
|---|---|---|---|---|
| `spravochnik` | 36 | 45 | 34 (76%) | 322/337 (96%) |
| `slovar` | 13 | 3 | 2 (67%) | 515/520 (99%) |
| `matematika` | 12 | 27 | 19 (70%) | 104/104 (100%) |
| `atlas` | 11 | 16 | 12 (75%) | 12/12 (100%) |
| `katalog` | 11 | 13 | 11 (85%) | 49/55 (89%) |
| `zhurnal` | 10 | 6 | 5 (83%) | 175/183 (96%) |
| **total** | **93** | **110** | **83 (75%)** | **1177/1211 (97%)** |

The instruments still print Russian; where this file quotes what a tool prints,
the quote is kept in Russian verbatim so it can be grepped against the real
output. Everything else is English.

## 1. Merging is a property of the TABLE, not of adjacency

"The detector pulls into a table's box everything standing beside it
horizontally" is far too broad. A census of every pair of boxes standing side
by side across the 36 pages of the handbook:

| label pair | pairs | label pair | pairs |
|---|---|---|---|
| text — text | **98** | figure_title — table | 4 |
| image — text | 8 | image — image | 1 |
| image — table | 4 | chart — chart | 1 |
| figure_title — figure_title | 4 | **table — table** | **1** |

The model places boxes side by side perfectly well — 98 pairs of text columns,
pairs of figures, pairs of charts, a figure beside a table. **Only two tables
refuse to stand side by side**: the single such pair in 36 pages is where the
gutter shadow physically cut a table in half. The dictionary puts the question
point-blank: its columns are prose, yet by appearance closer to a table than
anything else (narrow column, short aligned lines, hanging indent, 4.8 pt
type), gaps from 26 points down to five — and **text recall is 515 of 520**.
The columns do not stick together even when flush. The cost of the defect, on
five cases at once:

| case | truth | model |
|---|---|---|
| `table_two_side_by_side` | 2 tables, 131-point gap | 1 box, 0.95 |
| `three_column_table` | 3 tables captioned TABLE 1/2/3 | 1 box, 0.97 |
| `table_leaders` | 2 tables on dot leaders | 1 box, 0.91 |
| `kat_two_side` | 2 narrow catalogue tables | 1 box |
| `table_tall_narrow` | table left, prose right | 1 box 0.86 **over the whole leaf** |

`table_tall_narrow` is the limiting form: on a page of "narrow table plus a
column of prose" the model returned ONE block covering the whole leaf and
called the prose a table too. Ten text blocks of the truth went unfound.

## 2. The threshold IS a lever — the earlier "not a lever here" was wrong

This refutes our own claim with our own data. `books detect` keeps the model's
raw output in full, all 300 rows per page, precisely so the threshold can be
replayed without recomputation. The replay over six books:

| threshold | artifacts | text | merges | splits | extra boxes | nested dup | inside an unfound | sum (old column) | boxes total |
|---|---|---|---|---|---|---|---|---|---|
| 0.70 | 77/110 | 1097/1211 (90%) | 11 | 5 | 11 | 0 | 6 | 6 | 1216 |
| **0.50** (native) | **83/110** | **1177/1211 (97%)** | **11** | **5** | **12** | **5** | **8** | **13** | **1351** |
| 0.40 | 86/110 | 1189/1211 (98%) | 10 | 5 | 14 | 8 | 7 | 15 | 1412 |
| 0.30 | 89/110 | 1203/1211 (99%) | 10 | 4 | 16 | 23 | 6 | 29 | 1526 |
| 0.25 | 92/110 | 1204/1211 (99%) | 9 | 3 | 19 | 30 | 5 | 35 | 1608 |
| 0.15 | 94/110 | 1208/1211 (99%) | 9 | 2 | 26 | 57 | 4 | 61 | 1913 |
| 0.10 | 97/110 | 1208/1211 (99%) | 7 | 1 | 53 | 106 | 3 | 109 | 2344 |
| 0.05 | 101/110 | 1208/1211 (99%) | 6 | 0 | 226 | 313 | 0 | 313 | 4391 |

From 0.5 down to 0.25 buys **nine more artifacts** for seven extra boxes; below
0.1 only the extras grow, 53 to 226 in one step.

**The last two columns used to be one, and that one was the sum of two
different disasters.** Nesting was once counted against every truth box in a
row; it is now split into "nested duplicate" (inside an artifact that HAS a
match — unsuppressed raw output) and "inside an unfound one" (inside an
artifact with no match at all — nothing to duplicate, the original does not
exist). On nine benches at the native threshold 94 = 25 + 69, i.e. 73% of the
old column was the second name; across all 39 truth/detector pairs
664 = 502 + 162, and all 162 sit on real artifacts the model never caught (111
pieces of a fragmented box, 48 a single clipped one, 2 eaten by text, 1 a
spill) — not one genuine duplicate among them. So the growth from 6 to 313 is
almost entirely NESTED DUPLICATE, while "inside an unfound one" does not grow
at all, it falls: softening the threshold breeds extras and does not cure the
shortfall. The recomputation was possible only because the raw dump is kept, in
the `raw` field of EVERY page file, 300 rows per page on all nine benches
(minimum score in `raw` 0.0069 against 0.5 in `blocks`); the replay repeats the
`DocLayout.read()` selection word for word and at 0.5 matches the saved
`blocks` byte for byte on 36 handbook pages of 36.

By name: for four of the handbook's misses the CORRECT box lies in the raw
output below the threshold — `table_tall_narrow` 0.331, `spread_table_wide`
0.269, `table_two_side_by_side` 0.048, `table_leaders` 0.067 (the last labelled
`content`). Same in the atlas: `atl_plate_only`, a full-leaf drawing, correct
`image` box at 0.311, NOTHING accepted but the caption; `atl_rotated_plate`
0.469, a miss by three hundredths.

**We do not move the threshold.** The project rule forbids thresholds tuned by
us, and it stands: the registry holds the native one, and every number in this
file was taken at it. The sweep does not say "set 0.25", it says "here is what
each step costs" — exactly what the metric was obliged to show.

## 3. What the model gets right, against expectation

Checked and NOT confirmed as trouble: two tables stacked vertically
(`table_two_stacked`, `kat_two_stacked`); a two-tier header with spanning
cells; a dense ruleless table, 62 rows by 9 columns with gaps the width of the
leading; a drawing flush against a table; two charts side by side; a halftone
photograph; notes in the outer margin; a single page rotated 90°; the
dictionary index, indistinguishable by eye from a table — not one spurious
`table` box on it; a catalogue table across the full measure with no prose
around it. Reading order: 99% agreeing pairs over 2566 pairs of the handbook,
100% on the mathematics book. The model's ranks are PER PAGE; folded into one
list across pages they give 33%, "worse than a coin" — a sign of a wrong
comparison, not of the model.

## 4. What the handbook did not show

**A matrix is a table.** `mat_matrix`: a 5×5 determinant and a 4×6 bracketed
matrix, both eaten by a text block (`eaten by text (display_formula) 2`). On
the paired page `mat_matrix_vs_table`, where a matrix stands beside a real
table of the same proportions, the model glued them into one box — it sees the
matrix precisely AS a table, rather than not seeing it.

**A tall fraction is cut in half.** `mat_tall_fraction`: four fractions of
numerator, bar and denominator; the model returns TWO `display_formula` boxes
for each. Split counter 4 of 4.

**An almost empty leaf loses confidence.** Atlas: where the measure holds only
a drawing and a caption, the best box on the drawing scores 0.31–0.47 and the
caption is called `footer` or `vision_footnote` (5 cases of 9). The model
appears to choose the caption class by position on the leaf, not by appearance.

**A footnote under a table is not found.** `katalog`: `footnote 0 of 2`. Same
in the handbook — 3 footnotes of 8 in the journal.

**A running head is TWO boxes, not one.** The model returns the left and right
words separately at 0.92 each, and it is right: half a measure of blank paper
lies between them. Our truth first glued them into one box and printed
"header 0 of 12" — accusing the model of our own granularity error.

**A dictionary entry is `reference_content`.** 204 pairs of 517: where the
truth says `text`, the model says `reference_content`. On the merits it is
right; this is a clash of CONVENTIONS, to be settled with a declared set of
synonyms, not counted as an error.

## 5. Aged paper costs seven points

Same handbook, same seed, profile `decayed` (show-through from the verso, dark
scan edge, twice the specks, JPEG 52). The skew is IDENTICAL in both profiles,
so the truth boxes match byte for byte on all 36 pages — verified by comparing
the truth files, so the difference belongs to the paper, not to shifted truth.

| | `old` | `decayed` |
|---|---|---|
| artifacts found | 34/45 (76%) | 31/45 (69%) |
| merges | 7 | 7 |
| splits | 1 | 5 |

Merging does not depend on the paper at all (7 and 7) — it is a property of the
layout. **Splitting grows fivefold.**

## 6. What this measurement does not say

Nothing about **reading characters**: the bench is drawn with a font, not
printed by letterpress. Nothing about **channel order at the model's input**:
the bench is achromatic, `_age` converts the page to grey, an RGB/BGR swap is
invisible on grey, and the order was taken from someone else's code and is NOT
confirmed by measurement. Nothing about **page curvature at the gutter**:
absent from the bench, because it is not affine, and approximate truth is worse
than none. And nothing about **whether the truth itself is correct**. Against
that there are only eyes: `books overlay`, and a leaf with the truth in solid
line and the model's guess dotted. In one session the bench lied with its boxes
SIX times, and not once did the number look ill.

## 7. Measured: PP-DocLayoutV3 is NOT an upgrade for us

`PP-DocLayoutV3` (July 2026, 33M parameters against V2's 53M, 130 MB of ONNX
against 214) is on paper a straight upgrade. Checked on the spot: **the same
preprocessing** (Resize 800×800, `keep_ratio: false`, `interp: 2`,
normalization "none"), **the same native threshold 0.5**, **the same 25 labels
in the same order** — the adapter runs it without changing a line, except one.
That one: V3 has **a different output shape**. V2 gives two tensors, boxes
`[N, 8]` (last column duplicating the rank); V3 gives three, boxes `[N, 7]` and
a reading-order relation matrix `[N, 200, 200]`. The rigid unpacking
`out, _num = sess.run(...)` killed the run on the first page; the number of
outputs is no longer fixed, and the shape of the first is checked out loud.

| all six books, native 0.5 | V2 | V3 |
|---|---|---|
| artifacts found | **83/110 (75%)** | 81/110 (74%) |
| text and service | **1177/1211 (97%)** | 1075/1211 (89%) |
| merges | **11** | 15 |
| splits | **5** | 7 |
| boxes total | **1351** | 1694 |

An honest correction: the stock PaddleOCR-VL pipeline lowers the threshold to
0.3 under V3. The sweep over both models' saved raw output:

| threshold | V2 artifacts / text / boxes | V3 artifacts / text / boxes |
|---|---|---|
| 0.50 | 83/110 · 97% · 1351 | 81/110 · 88% · 1694 |
| 0.40 | 86/110 · 98% · 1412 | 86/110 · 90% · 2079 |
| 0.30 | 89/110 · 99% · 1526 | 90/110 · 91% · 2718 |
| 0.25 | 92/110 · 99% · 1608 | 92/110 · 93% · 3003 |
| 0.20 | 92/110 · 99% · 1727 | 95/110 · 93% · 3354 |

On artifacts V3 catches up by 0.3 and overtakes by 0.2. **On text it loses at
EVERY threshold** — 88–93% against 97–99%, nowhere reaching V2 — and for the
same recall it pays twice the boxes (3003 against 1608 at 0.25). Neither
version cures table merging: 11 against 15 at the native threshold, best
achievable by lowering is 8. **Newer is not better on our pages**, and the only
way to learn it was to measure — in the public tables V3 beats V2.

## 8. Merging is a property of the CLASS `table`, not of adjacency

Per page, across six books: on how many pages does the truth place two blocks
of one class side by side, and on how many of those did the model too.

| class | pages | separated | share |
|---|---|---|---|
| `text` | 31 | 24 | 77% |
| `header` | 5 | 5 | 100% |
| `figure_title` | 3 | 2 | 67% |
| `image` | 2 | 2 | 100% |
| `chart` | 1 | 1 | 100% |
| **`table`** | **3** | **0** | **0%** |

`table` is the only class the model never separated. The caveat, without which
the conclusion would outrun the data: `image` and `chart` have only two such
pages and one, and on those numbers "the table is special" cannot be told from
"the rest is barely tested". **The bench lacks pages with two figures and two
charts side by side** — that is the nearest work.

## 9. A second model, another architecture: merging is not cured by family

To tell "a flaw of RT-DETR with one-to-one matching" from "a flaw of Baidu's
training set, where tables are 1.18% and nearly all solitary", a second
independent model is needed. Taken: `docling-layout-heron` (IBM), **RT-DETRv2
on ResNet-50**, trained on **150k IBM documents**, input **640×640**, 17
classes, 171 MB of ONNX under Apache-2.0. Not one line of docling
postprocessing is applied — the graph is called directly. The adapter fitted
the existing `models/base.py` contract without changing it; what was needed was
an adapter registry (the `LAYOUT_ADAPTER` knob), a second label policy, and
three refusals out loud — on `do_pad`, on a class outside the vocabulary, and
on a missing native threshold.

**The error the bench caught.** The first run gave **0 matches of 110** — and
the zero was about me: `orig_target_sizes` for RT-DETR is (WIDTH, HEIGHT), and
I passed (height, width). The running head flew to x=1269 on a leaf 1012 wide.
The metric did not pretend the model was bad; it gave a flat zero that read at
once as "there is nothing to compare".

| book | PP-DocLayoutV2 | docling heron |
|---|---|---|
| `spravochnik` | 34/45 | **36/45** |
| `slovar` | 2/3 | 2/3 |
| `matematika` | **19/27** | 5/27 |
| `atlas` | 12/16 | **14/16** |
| `katalog` | **11/13** | 6/13 |
| `zhurnal` | 5/6 | **6/6** |
| **total** | **83/110** | 69/110 |

The total misleads: heron **wins on three books of six** and collapses on two,
each in its own way. On mathematics 14 formulas of 27 are "eaten by text" — one
`formula` class for every kind, and a display formula drowns in the paragraph.
On the catalogue six tables are "clipped": input 640 against V2's 800, and a
table the full height of the measure does not fit. And on the main question:

| case | truth | V2 | heron |
|---|---|---|---|
| `kat_two_side` | 2 | 1 box 0.98 | 1 box 0.67 |
| `table_two_side_by_side` | 2 | 1 box 0.92 | 1 box 0.92 |
| `three_column_table` | 3 | 1 box 0.97 | 1 box 0.95 |
| `table_leaders` | 2 | 1 box 0.95 | **2 boxes, 0.78 and 0.67** |

**The second model merges too — three cases of four**, being another
architecture, on other data, with another input. So it is not a peculiarity of
Baidu's sample. But neither is it a hard limit: on the fourth case heron split
the tables where V2 merged them.

## 10. Distorted input proportions are part of the trouble, not all of it

Both models squeeze the leaf into a square without preserving proportions: our
1012×1466 under V2 is compressed 0.79 horizontally and **0.55** vertically —
rows crushed nearly twice as hard as columns. Checked by feeding the same leaf
padded with white to a square (proportions intact, same model, same threshold):

| case | as is | squared |
|---|---|---|
| `kat_two_side` | 1 box 0.98 | **2 boxes, 0.87 and 0.85** |
| `table_two_side_by_side` | 1 box 0.92 | 1 box 0.96 |
| `three_column_table` | 1 box 0.97 | 1 box 0.97 |
| `table_tall_narrow` | 1 box 0.77 | 1 box 0.93 |

One case of four is fixed by the feed. That is NOT grounds for padding leaves
to a square in the pipeline — the model was not trained that way, and the
decision would be ours, not hers. It is grounds for knowing that part of the
defect lives in the feed, and for measuring it separately.

## 11. The gold bench: real pages, truth from librarians

The synthetic bench is about geometry and labels, not about print — that has
stood in its header from day one. Now there is a second, real one: **AnnoPage**,
**7550 annotation files for 5690** published pages of historical documents,
annotated by experts across 25 non-text categories. (This used to say "7550
pages" — a second instance of the same error as in the header of `annopage.py`;
the difference of 1860 is annotations for pages of other people's datasets,
which are not in the archive. The words about "the year 1485" and "Czech and
German" are removed: they are not in the archive, and there is nothing to
verify them with.) Zenodo 10.5281/zenodo.12788419, CC BY 4.0, 4964 MB.
Assembled by `books annopage raw/annopage` — an ordinary bench book, taken by
`detect`, `score`, `overlay`, `html` without a single change.

**What is annotated there and what is not.** Only NON-TEXT objects, 25
categories. There are no text blocks in the truth at all, so the report line
about text on this bench says `NOT MARKED` rather than "zero": those are
different zeros, and the metric now tells them apart.

**We drew the boundary, and it is declared.** Of the 25 categories, eleven map
onto our vocabulary directly (`Table`, `Graph`/`Diagram`, `Photograph`/`Image`/
`Geometric drawing`/`Other technical drawing`/`Floor plan`, `Mathematical`/
`Chemical formula`, `Stamp`). Six are disputable (map, advertisement, sheet
music, handwritten note, caricature, barcode) — reducing them to `image` would
mean deciding for the model. Eight are inexpressible altogether (initial,
vignette, frieze, bookplate, half-title, printer's ornament, decorative
inscription, coat of arms): PP-DocLayoutV2's vocabulary holds nothing for them,
and a miss there would be a miss of the VOCABULARY. The disputable and the
inexpressible are NOT thrown away: they lie in the truth as a separate list,
and a model box landing on them goes into the counter "on an object outside the
measurement", not into "extras". Without that the extras counter showed 460
instead of 103 — three quarters of it penalties for a boundary we drew.

### The first number on real pages

The authors' held-out split, 600 pages, 1232 objects in the measurement (plus
538 disputable and 366 inexpressible). PP-DocLayoutV2, native threshold 0.5:

| label | found | share |
|---|---|---|
| `chart` | 114/166 | 69% |
| `display_formula` | 136/229 | 59% |
| `image` | 382/673 | 57% |
| `table` | 48/124 | 39% |
| `seal` | 18/40 | 45% |
| **total** | **698/1232** | **57%** |

The rows now SUM TO THE TOTAL and used not to: it read `display_formula 147`,
`table 67`, `seal 21`, giving 731 against a total of 698. They diverged for a
reason — by 33, exactly the number of PAIRS with a role mix-up, which the
instrument prints on a separate line (`display_formula -> inline_formula` 11,
`table -> {text 11, content 7, reference 1}` 19, `seal -> text` 3). The rows
were taken from one quantity (pairs) and the total from another (found); today
the instrument prints the second, and the table is reduced to it. Against 75%
on the synthetic bench — but that is not the main thing.

### Merging is 71% of ALL misses

Of 534 shortfalls, **378 are merges**: `image` 258, `display_formula` 71,
`chart` 46, plus tables. On real pages the defect the synthetics showed with
eleven cases turns out to be **the dominant mode of failure**, and not only on
tables. The cause is the sample, not the model: pages where two artifacts of
one label stand side by side number thirteen in the synthetics and one hundred
and thirty-eight in AnnoPage. My synthetic bench was measuring the principal
defect with noise — named in section 8 as the nearest work, now named with a
number. Hence `bench/hard` (`books subset`): 130 pages, **887 pairs of "two
artifacts of one label side by side"**, 104 MB — the sharpest slice of the
defect and the cheapest feed for a paid model.

## 12. Six architectures on one leaf

`kat_two_side`: two tables with 164 pixels of clean paper between them.

| detector | architecture | input | `table` boxes |
|---|---|---|---|
| PP-DocLayoutV2 | RT-DETR-L + pointer network | 800×800 | 1 over both, 0.98 |
| PP-DocLayoutV3 | RT-DETR + masks | 800×800 | 1, right only, 0.59 |
| PP-DocLayout_plus-L | RT-DETR-L | 800×800 | 1 over both, 0.65 |
| docling heron | RT-DETRv2 R50 | 640×640 | 1, left only, 0.67 |
| docling egret-m | **D-FINE** | 640×640 | **0** |
| YOLOX-l | **not DETR, with NMS** | 1024×768 padded | 1 over both, 0.71 |

**Not one of the six returned two boxes.** Three architecture families, two
vendors, three training sets, three input sizes, the only model that preserves
proportions — one and the same failure. This is not a quirk of Baidu's weights.
A side observation which is NOT a proposal: V3 found the right table, heron the
left, and together they give both. Assembling an ensemble would mean fixing the
model with our own hands, and the project rule forbids that — but it is worth
knowing.

## 13. The defect IS curable, and that was measured on a rented card

Six CPU detectors — RT-DETR-L, RT-DETR with masks, the previous generation's
RT-DETR-L, RT-DETRv2, D-FINE and YOLOX — returned ONE box on a page with three
tables separated by gaps of clean paper. It held across three architecture
families, two vendors, three training sets and three input sizes, and looked
like a property of the task rather than of the model. **dots.ocr returned
three.** A generative 3B model (MIT), `layout_only` mode, greedy decoding,
RTX 4090 at $0.348/hour:

```
truth:    [80,458,238,636]  [384,459,542,638]  [688,461,846,640]
dots.ocr: [77,455,231,637]  [371,455,526,637]  [669,455,826,637]
          IoU 0.92           IoU 0.81           IoU 0.75
```

All three matched. On `bench/hard36` (36 pages, 747 pairs of "two artifacts of
one label side by side" — 84% of all pairs on the bench):

| detector | found | share | merges |
|---|---|---|---|
| **dots.ocr** (3B, card) | **149/403** | **37%** | **196** |
| docling heron | 88/403 | 22% | 294 |
| PP-DocLayoutV3 | 83/403 | 21% | 268 |
| PP-DocLayoutV2 | 80/403 | 20% | 307 |
| docling egret | 77/403 | 19% | 284 |
| PP-DocLayout_plus-L | 71/403 | 18% | 314 |
| YOLOX-l | 38/403 | 9% | 283 |

**The column was recomputed with the current instrument.** It used to read
heron 83 and egret 75 — the numbers from BEFORE the downscale-filter fix in the
adapter (section 15 calls them 88 and 77, and the sections contradicted each
other in plain text). Five rows of seven reproduced to the digit, the two named
ones moved; heron rises to second place, and their merges fell too: 298 -> 294
and 304 -> 284. That is **1.7 times more finds** and a third fewer merges than
the best of the free ones; this used to say "twice", which rested on the stale
heron — 149 against 88 is 1.7, not 2.0. The dots.ocr authors' claim, "without
supervision of the reading order the model does not perceive boundaries and
wrongly unites separate elements into one box", was confirmed against our truth.

**What this does NOT mean.** dots.ocr's splitting is on the contrary the
highest of all (13 against zero for five detectors), it has as many extra
boxes, and it costs money: 20.7 seconds per page on a 4090 against 2.5 on the
CPU, i.e. 36 pages for $0.118. Its reading order is generation order, and
reproducibility is untested. Replacing level one with it is not justified; what
is justified is the thought that the defect is NOT the limit of the task.

### What this measurement cost

Thirteen runs, $0.52, two of them useful. What surfaced along the way — every
trap OURS, not one of them the model's:

1. `mm_token_type_ids`: new `transformers` return a key the model's remote code
   does not expect. Version pinned to 4.51.3.
2. **The dot in the name `dots.ocr`** breaks the remote-code loader: the
   relative import dies with `No module named
   transformers_modules.rednote-hilab.dots`. The weights go into a directory
   named `DotsOCR` — after that the model comes up in 3 s.
3. Out of video memory: a page of 4.9 Mpx against the expected one, and
   attention softmax asked for 5.42 GiB. The feed is now capped at a declared
   size.
4. **The loop variable in `for k, item in enumerate(...)` clobbered the scale
   factor `k`** — and 36 pages of 36 were recorded as "unparsed", although the
   model had answered flawlessly. What saved it: the raw answer is kept in
   full, so the parse was replayed at home with no new rental. This is exactly
   the case the evidence is kept for.

Plus three troubles of the rental layer, found by running rather than reading:
on a failed rental, cleanup reached for `box` before it existed, and the real
cause hid behind `cannot access local variable`; **a dead offer killed the
whole run** instead of moving to the next machine; and the link rejection
threshold `MIN_LINK_MBPS` was not declared in the knob registry — on our
4.7 Mbit/s link it counted as 2.0, machines delivered 1.9, five rentals in a
row were rejected wholesale, and there was nothing with which to relax it
deliberately.

## 14. What we know about our own instruments, and what they do not measure

Section 6 is about the bench: what is missing from drawn pages. This one is
about the INSTRUMENTS: the metric, the mutation battery and the run stamp.
Measured on 28 August 2026 across all **44 "truth / detector output" pairs
lying on disk** (nine benches under PP-DocLayoutV2, six detectors on six
synthetic books, five on the gold bench, five on `hard36`, dots.ocr on
`hard36`).

**Three quantities of nine are silent more often than computed.** Reading order
is compared on **16 pairs of 44**, label confusion on **15 of 44**, text recall
on **38 of 44**. The silence is declared out loud (`NOT COMPARED`, `NOT
MARKED`), but the summary must be read knowing those shares: `egret` on the
handbook shares **0 of 21** labels with the truth, and the only thing that
survives the vocabulary boundary is ROLE confusion, **6 of 357 pairs**
(`metrics.label_alphabet`, `metrics.role_errors`).

**"No data" is a ninth of the battery's rows, and it is not "ok".** 44 pairs ×
23 probes = 1012 rows, of which **91 are "no data"**; at least one silent probe
appears on **38 pairs of 44**, most often "reading order reversed" — 28 pairs.
A probe with nothing to grip on honestly declines to run, but neither does it
confirm the metric on that pair. (The battery held 23 probes at the time of this
audit and prints **33** today, so the row count would come out different now;
the shares above belong to that measurement, not to today's battery.)

**"Uncaught corruptions: 0" is true of our nine V2 layouts — and only of
them.** Across all 44 pairs the battery gives **20 "NO" on 11 pairs**, all
twenty accounted for: 8 are `matematika/yolox`, where the baseline is **0 of
27** and there is nothing left to sag (a floor); 6 are the `TOUCH=1.01` probe
where every shortfall is ALREADY called "did not see it" ("0 against 0" on
`zhurnal/heron`, "27 against 27" on `matematika/yolox`); 1 is `slovar/egret`,
where the truth holds **three** artifacts and shifting the markup by a page
does not move 1/3; 5 are reading order on `PP-DocLayout_plus-L`, and that one
is a genuine find by the instrument, not a property of the sample. The battery
can fail and does fail, but its verdict must be read together with the baseline
— at the floor and at the ceiling it accuses the metric for the sample.

**The metric compares its two inputs, not the raster.** The book's sha256 is
compared only when `manifest.json` and `run.json` lie beside it: on **43 pairs
of 44**, uncompared on exactly one — the dots.ocr output, the very one that
cost $0.52 of rental. The raster is compared BY PAGE SIZE, `dpi` is merely a
label (`metrics._same_raster`): the same output recomputed from 144 dpi to 150
gives a share of 0.69 against 0.76 and an ordinary-looking list of troubles,
and at 180 dpi — 0.00.

**The metric's thresholds are ours, and not in the knob registry.**
`COVER_MATCH = 0.75`, `TOUCH = 0.10`, `TOL_PX = 6` pixels are constants in
`metrics.py`; they do not travel into the run stamp — the commit of the code
does. The tolerance is tied to `PAGE_DPI`: an eightfold `TOL_PX` does not move
the share on the handbook (76% against 76%) and does move it on the gold bench
(59% against 57%). The instrument has a grain of its own, and on real pages
that grain is visible. Nor does any bench stamp reproduce by commit: **9 of 9
are marked «+грязное дерево»** (`bench/*/detect/run.json`, the "commit" field).
The stamp says so out loud — but the numbers in this file will be restored not
by the commit, but by this same desk.

**What no probe catches** — the battery prints this itself, on its last line:
wrong TRUTH; a wrong coordinate transform by the model; a substituted book when
no stamp lies beside it; a label error WITHIN a role, if it is the same in the
truth and in the model. Against the first there are only eyes and `books
overlay`: in one session the bench lied with its boxes six times, and not once
did the number look ill.

**A healthy number can rest on a single page.** On `bench/hard36` text recall
prints as "100%", and that is `blocks 11, found 11 — counted over 1 pages of
36, text not marked on the rest`: the other 35 came from AnnoPage, where text is not annotated at all. The
caveat prints on the same line, and without it this would be the bench's best
figure.

## 15. Our own downscale filter cost five artifacts

The docling adapters took the `resample` filter code out of the weights and
passed it to cv2 as is. The codes are DIFFERENT: PIL 2 is BILINEAR, cv2 2 is
INTER_CUBIC. The page was downscaled with a filter other than the one used in
training, and there was nothing to notice it with: the boxes stay plausible.
Measured after translating the code through an explicit table:

| bench | heron before / after | egret before / after |
|---|---|---|
| `bench/hard36` (ninefold downscale) | 83 → **88** of 403 | 75 → **77** |
| `bench/annopage` | 695 → 694 of 1232 | 651 → **661** of 1232 |
| synthetic books | unchanged | slovar 1 → 2 |

The effect sits where the downscale is strongest: on the subset of real pages,
where a 5618-pixel leaf is squeezed to 640. On synthetics drawn for 1012 pixels
the filter decides nothing. This answers the review's objection "it may turn
out to be noise": not noise, but not an upheaval either — five artifacts of 403.

## 16. The metric was measuring OUR numbering as plus-L's reading order

`PP-DocLayout_plus-L` returns six columns instead of eight — it has no reading
order rank at all, and `order` in its pages is our own numbering of the graph's
rows. The adapter declared this in its FINGERPRINT, while `metrics._has_order`
reads the PAGE's `meta` and, finding no field, falls back to the default
`model_rank`. The result: across six benches it printed "reading order
agreement" of 29 / 36 / 41 / 44 / 46 / 44 per cent — numbers generated entirely
by our own numbering, and read as "plus-L reads the page in the wrong order".
That this was noise the battery showed itself: the probe "order reversed: did
it drop" gave NO on those same runs, because reversing OUR numbering raised the
agreement to 71 / 64 / 59 / 56 / 54 / 56 — the quantity wobbled around a half.
Now the adapter writes whose order it is into each page's `meta`, and the
metric prints `NOT COMPARED`. On V2, where the ranks are real, it was 2570
pairs at 99% and so it remains.

## 17. We were measuring the wrong thing for the pipeline

Every number up to here answers "did the model draw the box a human would have
drawn": two-sided coverage 0.75, a merge is a miss, an extra box is a miss.
Legitimate, but NOT our question. Ours runs: **will the object's meaning reach
level two.** It travels there as a cropped image, which does not care whether
the box is roomy or a neighbour wandered in — level two will take the image
apart into two blocks. It cares about one thing: did the content stay inside
the box. The difference came out fourfold:

| | strict match | object ink kept | objects whole | cropped as one image |
|---|---|---|---|---|
| hard36, PP-DocLayoutV2 | **20%** | **94.8%** | **91%** | **91%** |

Twenty per cent read as "the model finds almost nothing"; on those same 36
pages it keeps 94.8% of artifact ink and 91% of objects arrive whole. Both are
true — the first answered a different question.

### What is measured now: `books fitness`

Truth is not required. It counts by INK — dark pixels, threshold 160, the same
one the synthetic bench measures its truth with. Four quantities: **object ink
inside boxes of the artifact role** (this settles the "tighter than the
reference" argument — the margin around a figure holds no ink and costs nothing
to lose, while a cut-off table row is unrecoverable); **one box or two**
(something inside ONE box crops as one image, something spread across two
arrives in pieces and the table falls apart); **went off as text** (a box
exists but its role is textual, so the object never reaches level two and the
structure is lost — cured by a label, not a model); **ink outside ALL boxes**,
counted without truth on any book — what will simply vanish from the HTML.

Two guards, without which the number cannot be trusted. **Area under the
boxes:** one box over the whole leaf gives 100% of ink and 100% of whole
objects, so the share of the leaf under boxes prints beside it — honest markup
50–60%, degenerate 100%, and a battery probe checks exactly this. **The strip
at the edge:** on the gold bench 24.3% of ink lies outside all boxes, which
read as "a quarter of the book is lost"; half of it is a four-per-cent strip at
the leaf's edge — the dark border of the scan, not content — and that share
prints on its own line.

### Seven detectors on hard36 (the 36 hardest pages of the subset)

Of the 36 pages **35** are from the gold bench, the thirty-sixth synthetic
(`spravochnik`, p. 5) — and because of it `books score` on hard36 prints
"text 73%", counted from one page of 36.

| model | object ink | whole | bitten | torn | one image | as text | outside boxes |
|---|---|---|---|---|---|---|---|
| **PP-DocLayoutV2** | **94.8%** | **365 (91%)** | 4 | 28 | **365 (91%)** | **21** | 24.3% |
| docling-heron | 94.9% | 360 (90%) | 0 | 37 | 324 (81%) | 9 | 22.5% |
| PP-plus-L | 94.8% | 356 (89%) | 3 | 28 | 317 (79%) | 13 | 26.6% |
| docling-egret | 94.1% | 356 (89%) | 4 | 36 | 321 (80%) | 13 | 24.1% |
| PP-DocLayoutV3 | 89.9% | 338 (84%) | 0 | 57 | 308 (77%) | 0 | 30.0% |
| dots.ocr (3B VLM) | 88.6% | 238 (59%) | **76** | 48 | 201 (50%) | 1 | 32.6% |
| YOLOX-layout | 82.1% | 288 (72%) | 6 | 98 | 279 (69%) | 1 | 39.0% |

**"One image" and "as text" in the six lower rows were taken under the OLD
definition** (box geometry, not ink) and are not comparable with the top row:
V2's row was recomputed with the current instrument and gave 365 / 21 instead
of 331 / 11. The other six runs' directories were in a temporary place and were
wiped; recomputing costs a fresh detection. Every other column was taken with
one instrument and is comparable.

### Checked clean: the full AnnoPage, one and the same input

600 real pages downscaled to 1 Mpx — exactly the size dots.ocr squeezes its
input to internally. The truth was rescaled by the same factor, so both models
got THE SAME pixels and are measured against THE SAME truth. RTX 4090 rental:
2 h 24 min, $0.89, 8925 boxes in one pass.

| | object ink | lossless | crops whole | taken for text | part lost |
|---|---|---|---|---|---|
| **PP-DocLayoutV2** (CPU) | **94.0%** | **1025 (83%)** | 1021 | 83 ⚠ | **125** |
| dots.ocr 3B (rented) | 92.9% | 675 (55%) | 667 | **68** | 179 |

⚠ **THE "TAKEN FOR TEXT" COLUMN WAS TAKEN WITH A DEFECTIVE INSTRUMENT.**
`fitness` counted a pixel under TWO boxes twice — a sum instead of a union — so
an object part of whose ink was covered by nothing was declared "not lost,
curable by a label": an expensive trouble rewritten as a cheap one. Both rows
are recomputed. dots.ocr, on the same output that lies in git
(`bench/annopage-lite/dots-pages`, 600 pages), gives **68, not 82**; V2, which
has no output in git, was recomputed by a fresh `books detect` over the same
input (600 pages, 13 minutes on the CPU) and gives **83, not 87**. In both rows
the other four cells reproduced to the digit — 92.9 / 675 / 667 / 179 and
94.0 / 1025 / 1021 / 125 — so the defect touched exactly one column and the
ordering held.

The instrument also said out loud what the truth builder keeps quiet about:
**it counts 1230 objects, not 1232**, because two objects of the gold bench
have not a single ink pixel at 144 dpi (p. 102 `Table`, entirely off the leaf,
and p. 322 `Image` measuring 16.8 × 4.2 px). They stand in `books score`'s
denominator, and no model can find them. The V2 cell **87 awaits re-shooting**:
same kind, same defective code, and it cannot be rewritten by guess — that
costs one detection run on `bench/annopage-lite` (about 45 minutes on the CPU)
and a `fitness` check against `bench/annopage-lite/truth`. For orientation: the
same V2 on the full-size `bench/annopage` gives 90 → 86.

The section's other numbers are CHECKED AND STAND. Raw `docling-heron` was
recomputed in full — its own run over 600 pages, 15 689 boxes, exactly the
documented number — and all eighteen quantities matched to the digit: whole
1049, torn 127, object ink 94.5%, outside boxes 24.6%. Heron's doubling is
SINGLE-CLASS (879 pairs of 903 within one role), the duplicate lands in the
same mask, the union equals the sum — nothing to lie about; sections 18 and 19
need no recomputation. Excluding the 23 pages where the answer was cut off:
94.5% against 94.0%, 85% against 57% — the gap only widens. **That
answer-length ceiling is a property of the model, not a run failure.** On the
23 densest measures of the 600, generation hit the limit and cut the JSON off
mid-object; whole objects before the cut were salvaged by parsing in pieces —
3201 boxes, 139 per page — and every such page carries the field
`answer_truncated`. Without that mark a page with a cut-off answer would look
like a page where the model found less, and those are different things.

### Two consequences, and they pull in opposite directions

**dots.ocr was winning the WRONG metric.** On strict matching it led everyone
widely — 37% against 21% for the best CPU model (`PP-DocLayoutV3`; V2 has 20%).
By ink it is **behind**: 88.6% against 94.8%, and 76 objects "bitten" against
four, because it draws tighter than the reference and cuts content. Its real
virtue — 196 merges against V2's 307 — is worth almost nothing to us, because a
merge does not spoil the image. Section 13's conclusion that merging is curable
by training stands as a fact about models, but replacing level one with
dots.ocr is now rejected by measurement over all 600 pages rather than by
supposition: 675 whole objects against 1025, two hours of rented graphics card
lost to a laptop's CPU. Merging also **loses its priority**: it cost us not 71%
of the shortfall, as the strict metric read, but almost nothing. Dear are
**torn objects** (28 of 402 for the best) and **objects gone off as text** (21
under the current definition, 11 under the old): the first loses content for
good, the second loses structure.

**But ink alone cannot choose a model either**, and this correction is dearer
than the section. `books fitness` does not penalise merging BY CONSTRUCTION —
that was the design — yet it does not follow that merging costs nothing: the
docling vendor pipeline cost seven objects by ink (1049 → 1042) and one hundred
and thirty-two by the yardstick that sees merging (found 694 → 562, section
19). A nineteenfold difference, and a decision taken on one instrument would
have been taken wrongly. Hence the rule that was missing: **there is more than
one instrument, and all must be read.** `books fitness` — will the content
arrive; `books score` — did anything stick together; extra column jumps (a line
of that same `books score`) — will the book read in order. A model leading on
one column easily comes last on another: raw `docling-heron` leads on object
ink (94.5%) and is unfit entirely — every fourth block of its output is doubled.

### Synthetics: the same instrument on books with exact truth

| book | object ink | whole | one image | outside all boxes |
|---|---|---|---|---|
| katalog | 100.0% | 13/13 (100%) | 13 (100%) | 3.3% |
| spravochnik | 92.5% | 32/45 (71%) | 32 (71%) | 3.7% |
| zhurnal | 91.3% | 3/6 (50%) | 3 (50%) | 1.0% |
| slovar | 92.8% | 1/3 (33%) | 1 (33%) | 2.4% |
| atlas | 90.3% | 1/16 (6%) | 1 (6%) | 14.0% |
| matematika | 74.6% | 20/27 (74%) | 20 (74%) | 0.6% |

**"One image" here COINCIDES with "whole", and that is not a typo.** It used to
hold 40 / 5 / 2 / 12, taken under the OLD definition: box geometry against
"whole" by ink — two quantities on different footings in one row. Brought to
one footing (both by ink, differing only in whether the object is held by a
union of boxes or by one), they now diverge exactly where an object is REALLY
torn between boxes: none on the synthetics or `hard36`, so the columns
coincide, while on the gold bench the distinction is alive — 1014 against 1018
whole, "torn between boxes 4". `atlas` shows the instrument's boundary: "whole"
demands 99% of the ink, and a drawing's ink sits right at the edge of the truth
box — the model's box is a few pixels narrower and the object goes into
"bitten" (8 of 16) though it loses no meaning; the 0.99 threshold is named by
number and printed, and what remains to look at is the ink share (90.3%) and
"bitten". `matematika` is the opposite case, real trouble: 74.6% of ink, six
formulas torn — content is lost there.

## 18. The base is chosen: PP-DocLayoutV2, and it is NOT the leader on ink

Measured on the gold bench (600 real AnnoPage pages, 144 dpi, threshold 0.5).
Seven variants, including the docling vendor pipeline over heron and egret.

| variant | outside all boxes | at the edge | object ink | whole /1230 | dup pairs | VLM calls /pg | extra jumps /pg ² | whose order |
|---|---|---|---|---|---|---|---|---|
| docling-heron raw | 24.6% | 49% | 94.5% | 1049 | 4435 | 23.0 | 4.53 ³ | ours, in strips |
| heron + pipeline | 26.3% | 47% | 94.4% | 1042 | 19 | 14.6 | 0.79 | docling rules |
| docling-egret raw | 23.9% | 50% | 89.3% | 1039 | 3116 | 21.1 | 4.28 ³ | ours, in strips |
| egret + pipeline | 28.1% | 44% | 89.1% | 1030 | 12 | 14.6 | 0.86 | docling rules |
| PP-DocLayout_plus-L | 25.5% | 46% | 94.5% | 959 | 111 | 12.5 | 3.19 | ours, list position |
| **PP-DocLayoutV2** | 27.3% | 44% | 89.4% | 1018 | 174 | 15.9 | **0.83** | **model's rank** |
| dots.ocr ¹ | 27.7% | 38% | 92.9% | 675 | 5 | 18.0 | 0.71 | generation order |

¹ counted on `bench/annopage-lite` (the same 600 pages downscaled to 1 Mpx),
not on the full-size bench — different units, the row is unfit for comparison.
For reference, V2 on the same lite: 23.0% / 45% / 94.0% / 1025 / 195 / 15.9 /
0.88.

² **THE WHOLE "EXTRA JUMPS" COLUMN IS VOID until re-shot.** It was taken before
the instrument declared its grouping parameters and on a different denominator:
today's `books score` prints for V2 on the gold bench 501 jumps = **1.08 per
page over the 464 pages that entered the count, of 600** (930 transitions, 893
columns on 290 multi-column pages; 7891 boxes counted, 1920 full-width and 936
of other roles skipped; 136 pages of 600 unscored; grouping: x overlap 0.5,
full-width box 0.6 of the leaf, minimum 2 boxes per page) — where the table
says 0.83, and the overlap is now 0.5 where the first estimates used 0.25. The
ordering of the variants held on both denominators, so the section's conclusion
stands, but the numbers must be re-shot on the same seven directories; those
were in a temporary place and were wiped, so it costs a fresh detection, about
an hour on the CPU. **This is the only place in this file where that
caveat is recorded; `CLAUDE.md` keeps its own copy.**

³ Additionally taken under the bucketed sort `(round(y/20), x)`, which no
longer exists at `off` — section 20 measures that effect and finds it small.

**By ink V2 is not first — and it was made the base anyway.** What decides is
what the ink metric cannot see by construction: the merging of neighbours. By
the yardstick that penalises it:

| variant | artifacts found /1232 | meaning whole /1232 | merges |
|---|---|---|---|
| **PP-DocLayoutV2** | **698 (57%)** | **646** | **375** |
| docling-heron raw | 694 | 602 | 366 |
| heron + pipeline | 562 | 500 | 461 |
| docling-egret raw | 661 | 583 | 394 |
| egret + pipeline | 552 | 489 | 479 |
| PP-DocLayout_plus-L | 630 | 534 | 424 |

Raw heron leads on content and is unfit for a book: **4435 box pairs at
IoU ≥ 0.9** — every fourth block doubled — and an order giving 4.53 extra jumps
between columns. The vendor pipeline cures the doubling outright (19 pairs) and
brings the order to 0.79, but pays in merges: 366 → 461.

**The "outside all boxes" column does NOT distinguish models on real scans.**
All seven lie between 23.9% and 28.1%, and for each about half of that is the
four-per-cent strip at the leaf's edge, i.e. the black border of the scan. On
clean synthetics the same instrument gives 0.6–3.7%: a twenty-point gap that is
a property of the scan, not of the model. One cannot choose by this column, and
we used to.

### Reading order: V2 has its own, and that decides it

`PP-DocLayoutV2` is the only one of the SEVEN IN THIS TABLE that predicts
reading order itself (V3 was not in it and gives a rank too — section 7): the
page's `meta` holds `reading_order: model_rank`, and the ranks are real
network numbers (201, 202, 203… at `y0` 222, 2156, 2237). plus-L and both
docling models have no rank at all, and OUR rule assembles the book. How
expensive that is shows on plus-L: its boxes come out strictly by descending
confidence (100.0% of pairs over 200 pages), and "top to bottom" for them is
about half — a coin toss. Assembling a book on plus-L means shuffling the
paragraphs. (That second figure lived in FOUR copies and diverged: here it read
50.1%, `doclayout.py` and two places in `tests/test_order_contract.py` read
50.4%, on identical 100.0% and 3354 pairs. Which is right cannot be said — the
script that computed it is not in the tree, and the fix itself now blocks
reproduction, since plus-L no longer returns boxes in graph order — `order.py`
rearranges them. Both figures mean "a coin toss", so the number was replaced by
the word and the copies folded into here.) The same V2 output, re-sorted by our
key, gives **4.16** extra jumps against 0.83 by its native rank: the 0.83 was
earned by the rank, not by the geometry.

**And the quantity itself is a proxy without truth: reading order is not
annotated on any bench, 0 pages of 661.** AnnoPage has `order_marked: false`
on all 600 (there `order` is the line number in a file grouped by class), and
the synthetics do not state the flag at all. The instrument counts
transitions between columns and finds the columns by grouping on x-interval
overlap, so it is sensitive to those parameters: they are declared and travel
into the report, but the absolute number is tied to them. The first, hastily
written edition of the instrument gave 7.0 → 1.3 on the same boxes where the
current one gives 4.53 → 0.79 — the ordering of variants held, but a number
without declared parameters cannot be trusted.

## 19. The docling pipeline: what it buys and what it pays

`DOCLING_PIPELINE` switches on VENDOR code over the raw heron and egret boxes,
without a single edit of ours inside: `LayoutPostprocessor` (per-class
thresholds, overlap resolution, suppression of coincident pairs at IoU > 0.8,
nested boxes demoted to children of a wrapper) and `ReadingOrderPredictor`.
Three values: `off` (default), `post`, `full`. **The pipeline is shared by both
docling models** — one class for all their layout models (heron, heron-101,
egret medium/large/xlarge and the old v2), see
`docling/datamodel/layout_model_specs.py`. Installed as a separate dependency
set: `docling-slim` plus `rtree`, **+54 MB** to our environment (25 wheels,
510 -> 570 MB, measured with `du -sb`), without torch. The figure 242 MB, if
encountered, is those same packages with all dependencies in an EMPTY
environment, not the price of the set here. And **docling's reading order is
RULES, not a model**: the file is called `reading_order_rb.py`, "rb" for
rule-based, 740 lines of heuristics over boxes and not a single weight —
enabling the pipeline does not give heron a reading rank, it replaces OUR
sorting rule with THEIRS.

**The default is `off`, and here is why.** The pipeline buys exactly two
things, both monetary: duplicates 4435 → 19 pairs and VLM calls 23.0 → 14.6 per
page (−36%). It pays in content: whole objects 1049 → 1042, torn 127 → 135, ink
outside boxes 24.6% → 26.3%. And it pays three times more in merges: found
694 → 562, meaning whole 602 → 500, merges 366 → 461. Judging it by ink alone
would put the price at seven objects instead of one hundred and thirty-two;
that is exactly the error `books fitness` makes by construction, and `books
score` catches it.

**Mode `post` changes the order TOO, despite appearances.** The postprocessor's
last act is to sort the list itself, `_sort_clusters(mode="id")`, and on our
input that key degenerates into exact `(top, left)`: its first member
`min(cell.index)` does not work, we have no text cells at all
(`skip_cell_assignment=True` — we count by raster, not by a text layer).
Measured on `bench/slovar`: the `post` output matched a sort by (t, l) on 13
pages of 13, and our key on 3; 237 boxes out of place. And it is not free:
`post`'s order gives **474** extra jumps, while the same boxes left in our order
give **453**. `post` makes the order WORSE; only `full` fixes it. That sort is
STORAGE order, and the vendor says so directly — their comment "Semantic
reading order is predicted later" stands right beside it.

**Three traps, each of them silent.** The origin: our boxes run from the top
left corner, while the order rules compare elements through `self.b > other.b`
and expect an origin at the BOTTOM; feed them as is and you get a book read
bottom to top, and no box metric will notice, because the boxes are the same.
The label vocabularies: heron writes in snake case, egret in display names
(`Page-header`, `Document Index`) — one set of 17 classes written differently in
the weights, and the translation is declared name by name rather than derived by
a "lowercase it" rule, which would silently accept an eighteenth class from new
weights. Per-class thresholds: they stand first in the list of what the vendor
does, and on our input they remove NOT ONE box — minimum confidence 0.500328
against a maximum vendor threshold of exactly 0.5; the step comes alive only
below `LAYOUT_SCORE_THRESHOLD` 0.45.

**What was measured and is NOT broken:** the vendor does not touch the
coordinates of surviving boxes — 153 of 153 matched to the fifth decimal. The
rule "nobody fixes the model" is intact as far as coordinates go.

## 20. Book assembly order: our rule lost, and the measurement was honest

A narrow and monetary question. Two models of six predict reading order
THEMSELVES (`PP-DocLayoutV2` and `V3` — a real network rank). The other four —
`plus-L`, `heron`, `egret`, `YOLOX` — have no rank, and OUR rule assembles the
book. That rule lived in FOUR places across three adapters, and in two of them
it sorted by a key other than the one it declared:

| place | what it sorted by | what it put in `meta` |
|---|---|---|
| `doclayout.py` `our_order_key` | `(y0, x0)` | "ours, top to bottom and left to right" |
| `yolox_layout.py` | `(y0, x0)` | the same |
| `docling_heron.py`, two places | **`(round(y/20), x)`** | **the same** |

Twenty-pixel buckets are exactly the approach rejected in `doclayout.py` with
the argument "twenty is raster pixels: at a different `PAGE_DPI` neighbours
within a line swap places". Two rules lived under one name, and the only way to
see it was to read all four places at once. No check saw it — there were 169 of
them at the time, and 265 today; the count is beside the point, since none of
them looked across the four places.

### Experiment: the same boxes, three permutations

600 pages of the gold bench, `PP-DocLayoutV2` output, coordinates untouched to
the digit — ONLY the list rearranged. One `books score`, one denominator (464
pages in the count of 600):

| order | extra jumps | per page |
|---|---|---|
| ours `(y0, x0)` | **2471** | 5.33 |
| the model's own rank, V2 | 501 | 1.08 |
| docling's rules | **439** | 0.95 |
| docling's rules BLIND (all labels = text) | 454 | 0.98 |

Control: the "rank" variant gave exactly the 501 that `books score` prints on
the working output, so the experiment is set up correctly. The blind run shows
the gain comes not from our label translation but from the rules finding
columns: 439 against 454 is the price of the translation, and it is small.
`metrics.column_jumps_ranking` over 16 points of a sweep of the grouping
parameters then splits the answer in two:

```
RULER SPAN 4.02
ranges:  ours (y0, x0)     3.021 .. 7.041
         model rank, V2    0.229 .. 1.733
         docling's rules   0.284 .. 1.569
inverted pairs: "model rank V2 against docling's rules"
```

* **Our rule is worse than both CONSISTENTLY** — the limits do not overlap at
  all, at any of the 16 points. That is why it was replaced.
* **docling's rules against V2's rank the instrument does NOT distinguish**: the
  pair is inverted, the difference at the default is 0.13 against a ruler span
  of 4.02. So V2 and V3 KEEP their own rank — swapping something that works and
  is free for a 54 MB dependency, with no number in hand, is choosing by taste.

This is the point of the `_ranking_rule` the instrument prints itself: a pair
that diverges by less than the ruler's span is NOT DECIDED by this quantity.
The old argument "our rule is worse than graph order, 932 against 855" was
right in sign and unproven in magnitude, because it was made without the span.
The span itself depends on which variants are in the set: 4.02 for the three of
this section, while today's `books score` prints **5.27** for its own set of
four (`as_model_gave`, `top_down_left_right`, `column_by_column`,
`round_robin_columns`). Both are correct; they measure different sets.

### Why `(y0, x0)` loses, though it sounds right

On a two-column page it reads ACROSS the columns: a line of the left one, a
line of the right one, the left one again. Every such transition is counted by
the instrument as an extra jump, and counted fairly — a book folded that way
interleaves its columns.

### What was done, and what `docling` costs

The rule moved to `src/booksmith/order.py`, one for the project, chosen by the
`ASSEMBLY_ORDER` knob (`ours` | `docling`). The default is `ours` — not the best
by number, and for one reason: `docling` is a package, and `books detect
--adapter yolox` in a fresh environment must not fail over a sorting rule. The
`ours` rule needs no labels at all and does not consult the policy; docling's
rules look at exactly EIGHT names (`caption`, `code`, `footnote`, `page_footer`,
`page_header`, `picture`, `table`, `text` — taken by reading
`reading_order_rb.py`), and the translation for each of the five vocabularies is
declared name by name rather than derived from the role: the role answers "crop
it or print it", while the rules need "running head or running foot", and the
role "service" does not distinguish them. **This is NOT fixing the model** —
coordinates are not touched, not one box is merged, cut or deleted, only the
order of the list changes, and that was always ours. Verified on `bench/slovar`
with yolox: the box set is identical on 13 pages of 13, 406 boxes rearranged,
extra jumps 431 → 276.

What `docling` costs: the `docling-slim` and `rtree` packages, +54 MB (without
torch); and **the order depends on the python version** — `reading_order_rb.py`
has two non-transitive `sorted()` calls (lines 535 and 556), and on the same 600
pages the order diverged on THREE pages between python 3.12.3 and 3.13.13, the
boxes identical to the last digit. The version travels into the stamp, so the
divergence is at least visible.

### Second experiment: on a genuinely rankless detector

The experiment above ran on V2's boxes — a model that has a rank. For
completeness it was repeated on `docling-heron`, which has no rank at all and
for whose sake the rule was being changed. One run over 600 gold-bench pages,
three permutations offline, one `books score` (519 pages in the count):

| order | extra jumps | per page | limits over 16 points |
|---|---|---|---|
| old bucketed `(round(y/20), x)` | 2718 | 5.24 | 3.270 .. 6.697 |
| our declared `(y0, x0)` | 2741 | 5.28 | 3.318 .. 6.697 |
| **docling's rules** | **670** | **1.29** | **0.490 .. 1.936** |

```
RULER SPAN 3.428
inverted pairs: "ours (y0, x0) against the former bucketed key"
```

**The two "our" rules the instrument does NOT distinguish**: the pair is
inverted, the difference at the default is 0.044 against a span of 3.428.
Replacing the buckets with the declared key by itself improved nothing and
spoiled nothing — it fixed a DISCREPANCY BETWEEN WORD AND DEED, not a number,
and that is how it must be read. This also settles footnote ³ of section 18:
the `docling-heron raw` (4.53) and `docling-egret raw` (4.28) cells were taken
on the bucketed sort, but the change from it is within the ruler's play; what
moves those cells is the denominator of footnote ². The `egret` row was not
measured this way — the same result is expected by construction, but that is an
expectation, not a measurement, and it is written down here as such.

**docling's rules are better than both CONSISTENTLY** — the limits do not
overlap with either at any of the 16 points, and the gain is fourfold
(2741 → 670). On a rankless detector it is larger than on V2, and that is
reasonable: V2's network rank already held the order, while here nothing did.
