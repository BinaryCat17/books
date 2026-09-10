# Models, and the verdict on each

What each model is, where it runs, and the decision. The numbers behind
the contour verdicts are in `METRICS.md`; nothing here restates one. The
dots.ocr records were not kept, so its verdict stands on this text alone.

## Layout detectors, level one

All six are ONNX on the CPU. Which one runs is decided by `LAYOUT_ADAPTER`;
inside the paddle family by `LAYOUT_MODEL_NAME`; the YOLOX weights by
`YOLOX_WEIGHTS`. Two of the six return a reading rank of their own; for the
rest the book is assembled by our rule in `src/booksmith/core/order.py`.
Each is served as an image of its own, `model-<name>` out of
`infra/models/layout-cpu/Dockerfile`, answering the model protocol; a run
through the image is the run of the same weights in process.

**PP-DocLayoutV2** is the base of level one. Chosen for being first by
objects found and by meaning kept whole on the golden bench, not for being
first by ink, where it is not. Second by merges. Returns its own rank.

**PP-DocLayoutV3** is newer and smaller, returns a sparse rank of its own,
and is worse than V2 on every synthetic book at every threshold, paying for
its text coverage with twice the boxes. Switching is one knob.

**PP-DocLayout_plus-L** has no rank of its own and the worst separation of
neighbours in the paddle family.

**docling-heron** carries the most object ink and delivers the most objects
whole, and is unusable for a book raw: it doubles boxes by the thousand.
The vendor pipeline, knob `DOCLING_PIPELINE`, removes the doubles and cuts
the calls to level two, and pays with more merges, fewer artifacts found and
a resorted order. Off by default. Its order rules are heuristics with no
weight in them.

**docling-egret** is the one detector that returned no box at all over the
two tables of the probe page.

**YOLOX-l on DocLayNet** has no selection threshold of its own, so ours
applies and the adapter says so. The weakest separation measured.

## dots.ocr, a layout model on a rented card

**dots.ocr** is the proof and is rejected as a replacement. It answered the
one open question: on a page with two tables separated by clean paper, every
CPU detector returned one box and dots.ocr returned three, so the merge is a
property of the model and training fixes it. As level one it crops tighter
than the truth and cuts content, is ten times slower, fragments far more
often, and hits its answer-length ceiling on dense strips. Its reading
order is the order of generation and does not compare with the rest. There
is no launch button for it, and nothing of it is in the tree; if a hybrid
proof is wanted it returns as an image behind the protocol.

## Reading models, level two

**PaddleOCR-VL** is served as `model-paddleocr-vl` out of
`infra/models/paddleocr-vl/Dockerfile`: vLLM behind describe and health,
the chat route passed through. It is in use and the only model paid for. It read a real book
end to end on a rented card, and `books apply` placed its answers into the
book. That run proves the pipe works and measures no quality: the run is not
reproducible from the repository, and quality cannot be measured yet for the
reasons in `docs/architecture.md`.

Three mechanisms inside the vendor's own pipeline suppress a table box when
a fragment of a page is sent: cross-class suppression of overlapping boxes,
nesting rules that delete a box mostly inside a heading, and an overlap
filter in which the larger box wins. They are named beside the reader in
`src/booksmith/processing/read/readers/paddleocr_vl.py`, and patching them
is forbidden by the first rule.

## Checked and rejected

- **PP-LCNet table classifier**: two classes, wired and wireless; it cannot
  say "not a table" and calls any paragraph one.
- **SLANeXt wireless**: fewer cells than the cell detector at several times
  the time per crop.
- **RT-DETR-L wireless table cell detector**: usable only as a gate.
  Clustering its cells into columns separates tables from paragraphs
  perfectly; it returns geometry only.
- **Lowering the other classes' thresholds** reduced the table boxes: more
  text boxes survive and suppress them.
- **The vendor's block-merging switch** excludes tables by construction and
  does not touch the symptom.
- **olmOCR-2**: fast and cheap, and rejected on two counts visible without
  truth: no figures at all, and a grid that drifts by a column. Cell count
  is not a measure of quality.
- **Mistral OCR**: as a reference its output is a second reading with errors
  of its own, and a figure measured against it is not a figure against known
  text.
