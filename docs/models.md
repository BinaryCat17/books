# Every model this project has measured, and the verdict on each

One place for the verdicts, because the same figures used to live in six files
at once and that is exactly how a second copy drifts: `698` sat in `CLAUDE.md`
twice, in `contour-notes.md` three times and in the source six more.

**What is here:** what each model is, where it runs, what it costs, what it
found, what it fails at, and the decision. **What is not here:** how a number
was obtained -- that is the laboratory journal, and every section points at
its part of it. Nor the warnings that belong beside the code they guard.

Nothing below is an opinion. Every figure has a command or a file behind it,
and the commands are named.

---

# Layout detectors -- level one

Six of them, every one ONNX on the CPU, no card needed. Which one runs is
decided by `LAYOUT_ADAPTER`; inside the paddle family, by `LAYOUT_MODEL_NAME`.

Two of the six predict a reading rank of their own (V2 and V3). For the other
four the book is assembled by our rule, `src/booksmith/order.py`, knob
`ASSEMBLY_ORDER`.

The two benches everything below is measured on:

* **`bench/annopage`** -- 600 real pages, truth by librarians, 1232 objects.
  Answers "does it merge, does it lose content".
* **`bench/hard36`** -- 36 hardest pages, 747 pairs of same-label artifacts
  side by side, 403 objects. Answers only one question: can it separate two
  neighbours.

## PP-DocLayoutV2 -- THE BASE OF LEVEL ONE

RT-DETR-L with a pointer network, 53M parameters, 214 MB (213 963 712 bytes),
25 label names, input 800x800. Predicts its own reading rank.

**Chosen, and not for being first by ink.** On 600 golden pages it is first by
objects **found** (698 of 1232, 57 %) and by whole meaning (646), against 694
and 602 for the nearest, raw `docling-heron`. By merges it is **second** --
375 against heron's 366.

| | ink of objects | lossless | crops whole | taken for text | part lost |
|---|---|---|---|---|---|
| PP-DocLayoutV2 (CPU) | 94.0 % | 1025 (83 %) | 1021 | 83 | 125 |

Extra column jumps: **501** over the golden bench, 1.08 per page counted over
464 of 600 pages. On `bench/hard36` it separates 80 of 403 (20 %) and merges
307 times.

Reproduce: `books score bench/annopage/truth bench/annopage/detect/pages`.
Method: `docs/contour-notes.md`, sections 11 and 18.

## PP-DocLayoutV3

33M against V2's 53M, July 2026, and it has its own rank too -- a sparse and
genuine one (11, 21, 24, 37 against V2's 259, 259, 260, 261); the entry
condition is wired into the adapter as `out.shape[1] >= 7`.

**Newer is not better, and that is measured.** On the six synthetic books it
is worse than V2 at every threshold of the sweep: text 89 % against 97 % at the
native threshold, paid for with twice as many boxes. On `hard36`: 83 of 403
(21 %), merges 268 -- slightly better at separating than V2, on a bench that
asks nothing else.

Switching is one knob, `LAYOUT_MODEL_NAME`, and three minutes of compute.
Method: `docs/contour-notes.md`, section 2.

## PP-DocLayout_plus-L

RT-DETR-L, 20 label names, 800x800. No rank of its own.
`hard36`: 71 of 403 (18 %), merges 314 -- the worst separation of the paddle
family.

## docling-heron -- RT-DETRv2 R50

17 label names, 640x640, vendor docling. No rank of its own.

**Best by content and unusable for a book.** Raw, it carries 94.5 % of object
ink and delivers 1049 of 1230 objects whole -- and produces **4435 pairs of
doubled boxes**. `hard36`: 88 of 403 (22 %), merges 294.

**The vendor pipeline, `DOCLING_PIPELINE`, buys two things with money and pays
with meaning.** Doubled pairs 4435 -> 19, VLM calls 23.0 -> 14.6 per page. It
pays with merges 366 -> 461 and artifacts found 694 -> 562, and its `post`
mode also resorts the boxes, costing 474 column jumps against our 453. Off by
default. The order rules it brings are `reading_order_rb.py`, 740 lines of
heuristics with not one weight -- rules, not a model.

Installed by `pip install -e ".[docling]"`: +54 MiB to the environment, 25
wheels, no torch.
Method: `docs/contour-notes.md`, section 19.

## docling-egret-m -- D-FINE

17 label names, vendor docling. The only one of the six that produced **zero**
boxes over the two tables of the probe page.
`hard36`: 77 of 403 (19 %), merges 284.

Its fingerprint reported itself as heron until 2026-09-06: `getattr(self,
"полное_имя", "docling-layout-heron ...")` survived the identifier rename as a
string and fell through to its default. Silent by construction -- a `getattr`
with a default cannot fail.

## YOLOX-l -- DocLayNet

Not a DETR: duplicates are suppressed by NMS at 0.45, the threshold taken from
the reference YOLOX code. 11 label names, input 1024x768 padded.

**It has no native SELECTION threshold at all**, so ours applies --
`LAYOUT_SCORE_THRESHOLD = 0.5` -- and the adapter says so out loud rather than
implying a vendor default.

`bench/annopage`: 82.1 % ink, 288 of 403 lossless (72 %).
`hard36`: 38 of 403 (9 %), merges 283 -- the weakest separation measured.
Weights are chosen by `YOLOX_WEIGHTS`.

---

# Reading models -- level two

## PaddleOCR-VL -- IN USE, AND THE ONLY ONE PAID FOR

The reading model of level two. Runs on a rented card; `books read` is the
only command in the project that spends money.

**What it has actually done:** 436 pages read over eight rentals, two of them
successful, **$0.545**. 915 078 characters, 6906 model answers in 436 files.
From that, `books apply` placed **412 swaps** into "Технология огнеупоров" --
248 latex, 104 otsl, 60 text -- out of 488 extracted artifacts.

**The caveat without which that number lies:** the run is not reproducible
from the repository. The snapshot and the output live outside git, the commit
in the snapshot is `f92b55a` plus a dirty tree, and the reading directory was
rescued from another session's temporary directory into
`processed/vl-reads/`. It is proof that the pipe works, not a measurement of
quality -- and quality cannot be measured yet at all, for the three reasons in
`docs/limits.md`.

The adapter is `models/paddleocr_vl/reader.py`; the rental job is `spec()`
beside it. Its prompts are byte-for-byte from the vendor card and all ASCII.
Method: `docs/ocr-notes.md`.

## dots.ocr -- THE PROOF, AND REJECTED AS A REPLACEMENT

3B parameters, MIT, run in layout-only mode on a rented RTX 4090.

**Why it exists in this project.** It answers the one open question. Six CPU
architectures -- three families, two vendors, three training sets -- on a page
with two tables separated by 164 pixels of clean paper returned **one box, not
once two**. dots.ocr returned **three**, at IoU 0.92 / 0.81 / 0.75. On
`hard36` it separates **149 of 403 (37 %)** against the best local 21 %, and
merges **196** against 268-314. So the merge is a property of the model and
training fixes it -- which is what the authors claim, and it is now checked.

**And it is rejected as level one, also by measurement.** Over all 600 golden
pages, the same input, the same truth:

| | ink of objects | lossless | crops whole | taken for text | part lost |
|---|---|---|---|---|---|
| PP-DocLayoutV2 (CPU) | 94.0 % | **1025 (83 %)** | 1021 | 83 | **125** |
| dots.ocr 3B (rented) | 92.9 % | 675 (55 %) | 667 | **68** | 179 |

It crops tighter than the truth and cuts content, is ten times slower,
fragments four times as often, and on 23 dense strips hits the ceiling on
answer length. Its reading order is the order of generation, and that was
measured on a different bench, so it does not compare with the rest.

**What it cost:** 16 rentals named `dots-layout`, **one** of which succeeded.
The successful one $0.892; all sixteen **$1.370** -- quote the second when
asking what the measurement cost, because the fifteen failures are two thirds
of the bill. One pass: 2 h 24 min, 8925 boxes.

**Status: no launch button.** The word `dots` does not appear in `cli.py` and
`spec()` is called by nothing; it will become runnable when a model selector
exists. Two of its knobs are read past the registry, so a run using them is
silently unrepeatable, and declaring them belongs with that CLI branch. The
directory is kept for the four traps that ate the fifteen failed rentals.
Method: `docs/contour-notes.md`, section 13.

---

# Checked and rejected

Every one rejected on a measurement, and each is worth knowing so it is not
tried twice. The full workings are in `docs/ocr-notes.md`.

**`PP-LCNet_x1_0_table_cls`** -- unusable. Two classes, "wired" and
"wireless"; it cannot say "this is not a table" and confidently calls any
paragraph one, 15 out of 15.

**`SLANeXt_wireless`** -- not worth it. 143 cells against 176 from the cell
detector, at 11.9 s per crop instead of 2.0.

**`RT-DETR-L_wireless_table_cell_det`** -- usable, but not as a second
opinion: where we cope it adds nothing. Its value is as a GATE -- clustering
the cells it finds into columns gives >= 3 columns for 18 of 18 tables and 0
of 15 paragraphs, a perfect separation. Geometry only; the text stays the
VLM's job.

**olmOCR-2-7B** -- 47 s for 20 pages, $0.083 per run including rent, worked
first try. Rejected on two counts, both visible without any ground truth: no
figures at all (a 68 KB parse against 1.3 MB, 34 extracted figures against
zero) and a drifting grid (five columns instead of three on p. 309, a shift by
one position on p. 318).

**Mistral OCR** -- the former reference, and the reason a whole layer of this
project was deleted. Quality numbers used to be measured against ITS output
rather than against known text; that is a second reading with errors of its
own (`Pool Room Lathes` for `Tool`, `(1)`/`(2)` for `(±)`), and the reference
file is gone, so not one of those numbers can be reproduced. On Table TEDS,
PaddleOCR-VL-1.6 takes first place at 94.76; Mistral OCR scores 55.85 on the
same metric.
