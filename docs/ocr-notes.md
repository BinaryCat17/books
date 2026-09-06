# Document structure: how it is built and where it breaks

About PaddleOCR-VL and what is known of its behaviour on old technical
reference books: dense two-column setting, tables with **not one rule in
them**, columns held together by space alignment. Observed on
`bench/real/tables20.pdf` — 20 pages of a machine-tool reconditioning manual,
letterpress of the fifties on yellowed paper.

**Two thirds of this file were deleted, by one rule.** Everything measured
against Mistral OCR output is gone: that was a second reading with errors of its
own (p. 311 `Pool Room Lathes` for `Tool`, p. 314 `(1)`/`(2)` for `(±)`), its
denominator was taken with selection, and both the reference file and the run
directories are deleted, so not one of those numbers can be reproduced. Gone
too: the techniques now forbidden — re-asking, switching NMS off, multi-look,
inserting `⚠` and `<mark>` into the markup. What stays needs no ground truth.
Paid for in crashes: `docs/lessons-from-deleted-code.md`. Measured on contours:
`docs/contour-notes.md`.

## The pipeline end to end

```
PDF --render 2.0 (144 dpi)--> 1012x1466
    --Resize 800x800, keep_ratio: false--> detector PP-DocLayoutV2 (ONNX)
    --boxes--> postprocessing (threshold, NMS, nesting, unclip, order)
    --filter_overlap_boxes--> crop along the box, NO margin
    --shrink to 1 Mpixel, JPEG 75--> VLM 0.9B, prompt "Table Recognition:"
    --OTSL--> convert_otsl_to_html --> HTML
```

The model returns **OTSL**, not HTML and not Markdown: six tags `<fcel> <ecel>
<nl> <lcel> <ucel> <xcel>`. The prompt is exactly two words, no system message,
no statement of the format. If the answer is not OTSL, the converter returns an
empty string and raw text goes into the document.

## The root: the detector sees the page squashed

`~/.paddlex/official_models/PP-DocLayoutV2_onnx/inference.yml`:

```yaml
Preprocess:
- interp: 2
  keep_ratio: false      # proportions are NOT preserved
  target_size: [800, 800]
```

The ONNX graph input is declared rigidly, `image [N, 3, 800, 800]`, and cannot
be configured: both available models are in `STATIC_SHAPE_MODEL_LIST`, setting
`img_size` trips an assert, and the pipeline separately forbids a third model
(`assert model_name in ["PP-DocLayoutV2", "PP-DocLayoutV3"]`).

A 1012x1466 page is compressed 0.79 horizontally and **0.55** vertically. Line
spacing — the only feature by which a row of an unruled table differs from a
line of a paragraph — suffers the most. Raising
`PADDLE_PDX_PDF_RENDER_SCALE` for detection is pointless, it hits 800x800
regardless; it only affects the quality of the crop sent to the VLM.

## Three independent fuses that put out a table

Each is reasonable on its own; all three strike the same class of document.

**1. NMS, `iou_diff=0.98`** (`object_detection/processors.py:613`). A box puts
out a box of a *different* class at 0.98 overlap. A text box at 0.95 over a
table box at 0.49 overlaps by exactly that much.

**2. Nesting, `layout_merge_bboxes_mode`**
(`layout_analysis/processors.py:835`). In the 1.6 config the classes `chart`,
`display_formula`, `doc_title`, `inline_formula`, `paragraph_title` get mode
`large`: any box with >= 90 % of its area inside such a box is deleted silently
(`is_contained`, iou >= 0.9). On a FRAGMENT of a page the heading takes four
times the share of area and eats the table whole.

**3. `filter_overlap_boxes`** (`paddleocr_vl/uilts.py:108`). Above 0.7 overlap
there are guards for pairs like {table, image}, but {table, text} falls
straight past them — the larger-area box wins, which is the text one.

Fixing this at our end is not allowed: patching someone else's pipeline over
its own output is exactly the patch that hides a defect from the measurement
(`CLAUDE.md`, `models/base.py`).

## Small things worth knowing

Properties of someone else's library that the second-level reader lives with.

- The comments on the class list in `PaddleOCR-VL-1.6.yaml` **lie** (they say
  `9: footer`, `13: header`, `23: text`); the real labels are in the weights'
  `label_list`. Index 21 = `table` is correct in both.
- Under ONNX Runtime the detector returns no masks, and `layout_shape_mode`
  degenerates forcibly to `"rect"`. The polygon branches are dead code.
- The pipeline lowers `max_new_tokens` to 4096 where the model's own constants
  say 8192. A cut-off on a long table gives torn OTSL, and `otsl_pad_to_sqr_v2`
  then **silently truncates** rows longer than the "optimal width": a torn
  table comes back plausible and shortened rather than broken, and we have no
  instrument that tells the two apart.
- The crop is cut exactly along the box, no margin (`layout_unclip_ratio` =
  `[1.0, 1.0]`), and travels to the server as JPEG quality 75, no setting.
- The VLM has a LOWER entry threshold, `min_pixels` = 112896. A table crop at
  144 dpi is 375 x 66 = 24750 px, four times below it, and the pipeline
  stretches the crop by interpolation.

## Checked and rejected

**`PP-LCNet_x1_0_table_cls`** — unusable. It has two classes, "wired" and
"wireless"; it cannot say "this is not a table" and confidently calls any
paragraph a table (15 out of 15).

**`SLANeXt_wireless`** — not worth it. 143 cells against 176 from the cell
detector, at 11.9 s/crop instead of 2.0.

**`RT-DETR-L_wireless_table_cell_det`** — usable, but not as a "second
opinion": where we cope, it adds nothing. Its value is as a GATE — clustering
the cells it finds into columns gives >= 3 columns for 18/18 tables and 0/15
paragraphs, perfect separation. It returns geometry only; the text is still the
VLM's job.

**Lowering the thresholds of the other classes to 0.3** instead of the standard
0.5 **reduced** the raw `table` boxes from 20 to 17: more text boxes survive,
and part of the tables are put out on NMS. Counted from our own output, so no
ground truth is needed.

**`merge_layout_blocks=False`.** The parameter's description matches our
symptom word for word ("gluing boxes across columns"), but tables are excluded
from that gluing by construction:
`merge_blocks(..., non_merge_labels=image_labels + ["table"])`.

**olmOCR-2-7B** — 47 s for 20 pages, $0.083 per run including rent, worked on
the first try. Rejected for two reasons, both visible without ground truth.
First, **no figures at all**: a 68 KB parse against 1.3 MB, no `imgs`
directory, 34 extracted figures against zero. Second, **the grid drifts**:
p. 309 — five columns instead of three, a wrapped header pulled apart across
the extra ones; p. 318 — a shift by one position, a row of four values in a
three-column table. Hence a rule worth remembering: **cell count is not a
measure of quality**, since cells from a crooked grid count the same as
correct ones.

## What the model does with the illegible: it completes the pattern

Four feedings of one prompt over a single disputed cell. No ground truth needed
— what is measured is the model's behaviour, not agreement with another answer.

- **A blank white sheet.** The model produces complete tables — Chinese office
  templates (`项目名称 | 内容 | 发布日期`), **five different ones in five
  tries**. It is willing to invent out of nothing.
- **Only the right third of the page.** Five tries, five different pieces of
  nonsense (`20' to 24' (a.d.`, `"A" to "A"`). The column is objectively
  unreadable by this model.
- **The left two thirds.** With the third column removed, the model read the
  second as `12" to 15" Inc.` — correct. With the full context it read `18"`.
  **Context spoils the reading**: the neighbouring pattern overrides the
  picture.
- **Resolution.** At 576 dpi it got WORSE than at 288: `U to .0005"` instead
  of `0 to`, `.0606` instead of `.0005`. The optimum feed is near the
  resolution the model was trained at, not the native resolution of the scan,
  and it is not monotonic.

The ink is there all the while: at 864 dpi the cell is readable by eye. The
information exists; the model does not take it at any resolution. Weight does
not buy the ability to doubt — but legibility and calibration are different
things, and on a faded typeface capacity is exactly what decides. The
systematic misses on this typography (`Laths` for `Lathes`, `mch`/`mth` for
`inch`) are precisely the class of error cured by fine-tuning, not by choosing
a feed. In short: invention cannot be removed, but it can be detected —
isolating the column plus resampling gives five different answers out of five.

## What catches invention, and what does not

**Token probabilities do not catch it, by construction.** vLLM returns a
logprob per token (`logprobs=True`). Tokens below -1.0 (~37 % probability) can
be flagged: 5 cells were flagged, all five genuine READING errors, zero false
alarms. But the invented value was not flagged and could not have been — a
hallucination is by definition high-probability, it fills the gap with the most
plausible thing rather than a random one. Logprob measures confidence in the
continuation, not in the reading, and the model draws no distinction between
the two.

**Self-consistency does catch it.** Three readings of the same PDF at
`temperature=0.4`: of 270 cells, 217 were identical in all three, i.e. 80 %.
They diverge in no random place:

| page | cells agreeing | what it is known for |
|---|---|---|
| 304 | **2 of 23** | a value is invented here |
| 313 | 23 of 43 | two tables glued across columns here |
| 303 | 8 of 14 | the ± sign is lost here |

The two pages that took a whole day to find by hand turned out to be the top
two by instability. It costs a threefold count, but only over table crops, and
those are a small share of the calls.

**Important for any future metric:** a confidence flag is an instrument for
WORDS, not for NUMBERS. Measuring planted corruption gave a lift of 0.29–0.65
against a shifted row in all six books — a corrupted cell is flagged LESS often
than an average one. And the leading kind of invisible corruption is exactly
the shifted row, identical across passes, so divergence between passes cannot
see it by construction.

## Reading text inside figures: checked and rejected

paddlex has `use_ocr_for_image_block`, off by default: an `image` block is cut
out as a picture and nobody looks inside. The loss looks appreciable — diagrams
carry letter callouts, and the text beside them says "each end (A) and (B) of
the PARALLEL". We switched it on and ran it. The result is negative and
unambiguous:

- the callouts `A` and `B` were not read at all; in their place, the digit `1`;
- on pp. 307 and 308 the model produced `The quick brown fox jumps over the
  lazy dog.` — the school pangram out of its training data, invented whole
  from a line drawing;
- on p. 315 it fell into a loop, `1.` `2.` … `100.`;
- the hieroglyphs `千`, `一`, random `D`, `J`, `☐`;
- **+2100 words of garbage over twenty pages** in total.

A line drawing is noise to this model, and it does not know how to stay silent.
If the callouts are ever needed, take them not by blanket OCR over the picture
but by a detector for small text inside a figure — a separate model.

## The answer ceiling shows itself on the table of contents

The `content` block (the contents page) came out at 8200 characters, of which
**49.8 % are leader dots**, breaking off mid-word: the model emitted one entry,
went into repetition and hit the answer ceiling. Raising the ceiling is
pointless — a bigger budget buys more dots, not more entries.

The obvious move was to drop the `content` class by label, and that would have
been a generalization from one book: where the table of contents is short the
block reads normally, and dropping it loses content over another book's
misfortune. The model does see the structure in detail (539 pages):

| label | blocks | what it is |
|---|---|---|
| `paragraph_title` | 462 | `Sec. 1.1\nDefinition of Scraping` — number and title in ONE block |
| `figure_title` | 695 | `Fig. 4.2 A turn-table having means for tilting.` |
| `header` | 88 | `Chapter 1`, `THE ART OF SCRAPING`, `PREFACE` |
| `doc_title` | 4 | the book title and the titles of two chapters |
| `content` | 1 | the contents page |
| `vision_footnote` | 56 | callouts off drawings, `(1) Column (2) Elevating screw` |

## Two LABEL misses on a correct box

Separate from localization, and invisible to a metric that measures geometry.

- **P. 40** — a small table of dimensions was labelled `display_formula` with
  confidence **0.95**, and the VLM honestly returned it as an array of LaTeX.
  Content intact, markup wrong.
- **P. 4** — the table of contents, parsed as a list with leaders rather than a
  table. Content intact, and a list is more useful here; not a miss.

The class itself — a wrong label on a correct box — is confirmed independently
on the hand-annotated golden bench.

## Calibrating expectations

External numbers; they touch none of our runs. On a benchmark of real books
(Dr. DocBench, 4514 pages) the best system in the world gives TEDS **55.85**,
not the 94 it gets on OmniDocBench. PaddleOCR-VL-1.6
takes first place on Table TEDS (**94.76**); Mistral OCR on the same metric
gives **76.78** — weaker at recognition, but with no stage at which a table can
be lost to a wrong box.
