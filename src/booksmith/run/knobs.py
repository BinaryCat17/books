"""Knob registry: everything affecting a run is declared here and only here.

Carried over from the old `jobs/paddleocr/entrypoint.py` with its rules:

* `knob()` raises on an undeclared name instead of returning "". A knob read
  past the registry misses the snapshot too: the run turns unrepeatable
  silently, and silent trouble has no catcher here.
* a default is stored as a STRING, as the environment would hand it over.
  Otherwise the snapshot writes `2.0` where the run saw `"2"`, and comparing
  two runs trips over the type, not the value.
* a default lives in one place, here. A second copy in the job builder would
  mean a changed default never reaches the machine until someone remembers
  that file.

WHAT THIS FILE CANNOT DO, WHICH MATTERS MORE THAN WHAT IT CAN.

`VL_MODEL_DIR` -- the knob deciding which weights vLLM raises -- was NOT
caught by the registry but by the deleted `tests/test_knobs_registry.py`,
which parsed sources and `run.sh` as trees: the shell sets that knob by
`export`, it never passes through `knob()`, and `KeyError` cannot see it by
construction. Crediting the registry means believing yourself guarded where
there is no guard. The catcher is back HALFWAY: `readers()` walks the tree and
sees both forms -- `knob("NAME")` in python, `$NAME` in shell -- but only for
names ALREADY declared here. A name absent from the registry (the
`VL_MODEL_DIR` disease) stays invisible; catching it needs a list of legal
shell variables, and there is none.

HOW MANY AND WHO READS THEM -- DO NOT ASK THIS PROSE. A hand-typed tally
stood here twice and went stale both times; the second edition even carried
two counts of the same thing that could not both be true. What it missed were
live names -- `LAYOUT_ADAPTER` and `YOLOX_WEIGHTS` among them, and every
`books detect` takes those two. A list typed by hand lies within half a year,
silently, and people decide by it. So `readers()` counts, and one line prints
the tally:

    python -c "from booksmith.run import knobs; r = knobs.readers(); print(len(knobs.KNOBS), sum(1 for v in r.values() if v), len(knobs.debts()))"

The numbers are its to print and absent here ON PURPOSE: a number written in
goes stale silently, and this file has twice been the example. Readers
outnumber the python ones -- `models/paddleocr_vl/run.sh` takes some, and to
`readers()` the shell is as much a consumer as code.

TWO -- `PASSES` and `LOGPROBS` -- are declared DEBT, counted by `debts()`.
Here stood "three", `VLM_TEMPERATURE` third; that debt was cleared when the
second level arrived while the sentence stayed in the present tense. The debt
is a field, `debt=True`, not prose alone: "declared but dead" is the number
`len(debts())` and rides into the snapshot. `PASSES` is doubly in question --
the clean slate measured block boxes byte-identical across all three passes,
so passes do not affect localisation at all. Debt disagreeing with the tree is
caught by `audit()` from `books replay --check --selfcheck`, which prints the
count of disagreements as its own value rather than drowning it in "done".

THE LIST WAS EMPTIED ON PURPOSE. The old registry held twenty-three knobs, six
-- `MULTIVIEW`, `VIEW_NMS`, `PREFER_TABLES`, `SPLIT_COLUMNS`, `REASK`,
`KEEP_INNER_FILTER` -- switching on our patches over the model. Gone: the
model gives what it gives, and nobody downstream corrects its boxes. A knob
returns not because the model has one, but when the bench has shown it changes
something.

`LAYOUT_TABLE_THRESHOLD` went back to the native 0.5, not our 0.05, which came
from "3/6/9 tables at thresholds 0.5/0.2/0.05" counted against Mistral OCR
output. That reference is deleted and the denominator was selective -- a table
Mistral missed never entered it. Nothing to inherit; let the bench set it.
"""
import os
import re


class Knob:
    """One knob: name, default as a string, what for, and has it a consumer.

    `debt=True` means "declared, read by nobody" -- a deliberate debt, not a
    working setting. It used to be prose in the header: three names in a text
    nobody checks against the code. As a field it is counted by `debts()`,
    checked against the tree by `audit()`, and carried into the snapshot: prose
    is read by eye and from memory, a field can be produced as a number.
    """
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name, default, what, debt=False):
        self.name, self.default, self.what = name, default, what
        self.debt = bool(debt)


KNOBS = (
    # --- feed: the only thing measured without a reference that yielded ---
    # WHAT STOOD HERE AND WHY IT WAS WRONG: "measuring 144, 300 and 600 showed
    # no difference (379 boxes and 99.3% ink in all three)". It showed TWO
    # SUMMARY NUMBERS agreeing, and both are blind to dpi. Per page the box
    # count differs on 15 pages of 20, and 379 is no invariant: across ten dpi
    # values the band is 378..384. A zero from not understanding, passed off as
    # a zero from checking. The run itself IS repeatable -- two repeats at 300
    # dpi gave byte-identical blocks -- so the band is dpi, not noise.
    Knob("PAGE_DPI", "144",
         "the resolution a page is RENDERED to for detection. The "
         "detector squeezes the raster to 800x800 itself (keep_ratio: "
         "false). THERE IS A DIFFERENCE, just not in the summary numbers: "
         "on bench/real/tables20.pdf (20 pages) at dpi "
         "100/140/144/148/200/300/450/580/600/620 the boxes are "
         "384/381/379/378/380/379/378/378/379/379 (band 378..384, 379 "
         "falling out four times), ink under boxes 99.3% everywhere and "
         "99.4% at 100 -- both numbers blind to dpi. The run repeats: two "
         "repeats at 300 dpi gave byte-identical blocks, so the band "
         "378..384 is dpi and not run noise. The LABEL tells them apart: "
         "paragraph_title 42/41/39/40/39/38/36/34/32/34 -- a monotone "
         "decline four times wider than the noise of neighbouring dpi "
         "(39..41 at 140/144/148); text meanwhile stands still "
         "(236..241), so boxes are LOST, not carried over. The cause is "
         "not the resolution but the FILTER: the adapter squeezes the "
         "raster with cv2.INTER_CUBIC (interp: 2 from the weights), at "
         "600 dpi that is a 7.6-fold vertical shrink, i.e. subsampling -- "
         "4.3% of the halftones reach the net against 16.6% with "
         "INTER_AREA. Swapping the interpolation for INTER_AREA at 600 "
         "dpi brings paragraph_title back 32 -> 40 without moving the "
         "total (379), and takes a table away (5 -> 4); at 144 dpi the "
         "same swap gives 382 boxes and 3 tables instead of 5. No dpi and "
         "no filter adds a table. On box coordinates it tells directly"),

    # WHAT NOT TO DO, also measured. Raising dpi is pointless: 600 pays four
    # times the raster and twice the time, returns the same 379 boxes and loses
    # eight headings. Changing the interpolation in the adapter, likewise:
    # `interp: 2` is written in the weights' `inference.yml`, the swap would be
    # our patch over someone else's preprocessing, and it pays a table (5 -> 4
    # at 600, 5 -> 3 at 144) -- the very thing the project exists for.
    #
    # SEPARATELY, AND NOT dpi-DEPENDENT AT ALL: under `keep_ratio: false` a
    # 506x733 sheet is squeezed 1.4486 times harder vertically than
    # horizontally, so the net sees it at 78.6 dpi vertically against 113.8.
    # Line spacing -- the only cue by which a ruleless table row differs from a
    # paragraph line -- suffers most.

    # --- model and weights: without them a run cannot be repeated ---
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B",
         "model name for vLLM and for the client"),
    Knob("VL_MODEL_DIR", "", "VLM weights dir; run.sh sets it, vLLM reads"),
    Knob("LAYOUT_ADAPTER", "doclayout",
         "which detection adapter to call; the list is "
         "detect.py:ADAPTERS, four of them: doclayout (PaddleOCR "
         "PP-DocLayout*, 25 labels on V2/V3, 20 on plus-L), docling (IBM "
         "heron RT-DETRv2, 17), docling-egret (IBM egret D-FINE, 17), "
         "yolox (DocLayNet, 11). Different label dictionaries and "
         "different policies -- comparable only blind to the label"),
    Knob("YOLOX_WEIGHTS", "",
         "which YOLOX weights to take: yolox_l0.05.onnx (the default) or "
         "yolox_tiny.onnx"),
    Knob("LAYOUT_MODEL_NAME", "PP-DocLayoutV2", "layout model name"),
    Knob("LAYOUT_MODEL_DIR", "", "layout weights directory"),
    # A threshold for ALL classes at once, and a knob of its own rather than "a
    # table threshold", because in paddlex postprocessing a threshold dict with
    # one class silently gives the rest 0.5 -- so "lower the table threshold"
    # changed all twenty-five V2 classes. Our selection names classes one by
    # one, so the common threshold has to be named too.
    #
    # `LAYOUT_TABLE_THRESHOLD` is read by `models/doclayout.py` alone; in
    # `docling_heron.py` (heron and egret) and `yolox_layout.py` one threshold
    # covers ALL classes, `table` included ("table" in docling, "Table" in
    # DocLayNet) -- see their `thresholds()`: `{lab: common for lab in
    # self.labels}`, no second knob there at all.
    #
    # The default is the native `draw_threshold` of the PP-DocLayout weights.
    # docling and yolox have NO native threshold -- nobody wrote one into the
    # weights -- and their `threshold_drift()` honestly says "nothing to
    # compare against", which is not the same as "no drift".
    Knob("LAYOUT_SCORE_THRESHOLD", "0.5",
         "detection threshold. On doclayout -- common to every class "
         "EXCEPT table (24 of the 25 classes on V2/V3, 19 of the 20 on "
         "plus-L), the default native to the weights. On docling, "
         "docling-egret and yolox -- one for ALL classes, table included, "
         "and the weights carry no native threshold at all"),
    Knob("LAYOUT_TABLE_THRESHOLD", "0.5",
         "the native table detection threshold; read by doclayout ONLY -- "
         "in the other three adapters a table goes by "
         "LAYOUT_SCORE_THRESHOLD"),

    # --- DOCLING VENDOR PIPELINE over heron and egret boxes -----------------
    # `off` -- the model's boxes as they are. `post` -- vendor postprocessing
    # (`docling.utils.layout_postprocessor`: PER-CLASS thresholds, overlap
    # resolution, coincident pairs killed at IoU > 0.8, nested boxes moved into
    # the wrapper's children). `full` -- that plus reading order from
    # `docling/models/postprocessing/reading_order_rb.py`; "rb" is RULE-BASED:
    # 740 lines of RULES over boxes, not one weight. heron gives no reading
    # order either way -- the pipeline replaces OUR sorting rule with THEIRS,
    # and that may not be called a model.
    #
    # ALL NUMBERS BELOW ARE HERON'S. TWO adapters read the knob (`docling` and
    # `docling-egret`), it is measured on one. egret has other boxes and
    # another price: separate item at the end, not to be mixed in.
    #
    # THE BENCH SHOWED IT MATTERS. Gold bench, 600 real AnnoPage pages, heron
    # on CPU, one `off` run and one `full` (2026-08-29, python 3.13.13, docling
    # 2.123.1). `post` and `full` return THE SAME 9867 boxes, matching to the
    # coordinate, and differ only in order; so "-> ..." reads as "post and
    # full" for everything but jumps and reordering:
    #     boxes                    15689 -> 9867  (734 into wrapper children)
    #     duplicate pairs IoU>=0.9  4435 -> 19
    #     VLM requests per page     23.0 -> 14.6
    #     artefacts                 1869 -> 1095
    #     extra jumps, COUNT        2718 -> 471  (`post` 2243: it thins AND
    #                               reorders, but reorders WORSE)
    #     boxes reordered           ? -> 6232 of 9867, for `full`
    #     object ink kept          94.5% -> 94.4%
    #     objects arriving whole    1049 -> 1042 of 1230
    #     ink outside every box    24.6% -> 26.3%
    #     TORN objects               127 -> 135, i.e. they GROW
    #
    # JUMPS COMPARE BY COUNT AND BY NOTHING ELSE. `off`/`post`/`full` give
    # 2718 / 2243 / 471; over all 600 pages that is 4.53 / 3.74 / 0.79, but
    # today's `metrics.column_jumps` divides by the pages that entered the
    # count (519 / 443 / 443) and prints 5.24 / 5.06 / 1.06. Same counts,
    # diverged DENOMINATOR: numbers from different days reconcile only as
    # counts.
    #
    # THE REORDERED CELL IS A QUESTION MARK, NOT A DIGIT. `post` had a ZERO
    # there, and it was a zero from not checking: the counter ran only inside
    # the `full` branch. Fixed, then measured on three benches -- slovar 237 of
    # 531, matematika 8 of 153, hard36 162 of 708 -- but not on the gold one,
    # which costs forty-five minutes of heron. A question is honester than a
    # zero.
    #
    # THE PRICE BY A RULER THAT PENALISES MERGING -- missing here entirely.
    # Everything above is `books fitness`, which by construction does not
    # penalise merging: a wider box is no loss to it, which is why the price
    # kept coming out as "seven objects". Same two runs, same truth, another
    # ruler (`books score bench/annopage/truth <run>/pages`, 600 pages):
    #     artefacts found of 1232   694 -> 562  (-132)
    #     meaning whole of 1232     602 -> 500  (-102)
    #     MERGED                    366 -> 461  (+95)
    #     cropped 139 -> 138, called text 56 -> 58, unseen 69 -> 75
    # A hundred and thirty-two objects against seven -- nineteenfold, and it
    # decides the default, not the ink. The project has already paid for a
    # ruler answering the wrong question; this is that mistake from the other
    # end -- a soft ruler where the question was ABOUT merging.
    #
    # WHY THE NUMBERS WERE RECOUNTED. Their first record (15643 -> 9817,
    # duplicates 4392 -> 22, whole 1050 -> 1041, outside 24.8% -> 26.3%) came
    # from a run made BEFORE the shrink-filter fix in the adapter itself:
    # `resample` from the weights went to cv2 as a PIL number, so the page was
    # squeezed CUBIC instead of BILINEAR. The fix gave 15689 raw boxes instead
    # of 15643 -- 46 of difference, and everything downstream moved with them.
    # On that run's SAVED raw boxes today's code reproduces the old numbers to
    # the unit (9817 boxes, 770 into children, 22 duplicates, 1093 artefacts,
    # ink 94.3%, whole 1041): the input diverged, not the pipeline. One item
    # reconciles neither way, "extra jumps 7.0 -> 1.3": `metrics.column_jumps`
    # in its morning edition gives 4.49 -> 0.79 on those same saved boxes, and
    # no sweep of its parameters (overlap 0.5..0.99, through 0.6..1.01) lands
    # there. That metric was uncommitted work and its former edition is
    # unrecoverable; direction and factor of the fall match anyway, 5.7 times
    # against 5.4.
    #
    # THE DEFAULT IS `off`, AND NOT OUT OF TIMIDITY. Four reasons with a price.
    # 1. All six bench detectors are measured RAW. On by default, two of the
    #    six run with someone else's postprocessing and a comparison of
    #    architectures turns into a comparison of our builds. egret already
    #    suffered this: our argmax against the native D-FINE rule gave 470
    #    boxes against 529, and while the rules differed, heron against egret
    #    measured our parsers alongside the models.
    # 2. It PAYS IN CONTENT by both rulers; the figures are in the tables
    #    above. `books score`: 132 fewer artefacts found, 95 more merges.
    #    `books fitness`: seven objects of 1230 stop arriving whole, ink
    #    outside every box grows 1.7 points, eight more come back TORN. Here
    #    stood "127 instead of 135", reversed, and the price read as a gain;
    #    the measurement (`books fitness bench/annopage/annopage.pdf --detect
    #    <run>/pages --truth bench/annopage/truth`) gives 127 torn at `off`,
    #    135 at `post` and at `full`. What the first level did not outline will
    #    not be in the book; what it merged, the second level gets as one
    #    picture for two.
    # 3. With `full` the order is the VENDOR's rule, and swapping one rule for
    #    another silently is not allowed: the metric reads the "reading order"
    #    field and, on the word "ours", decides whether to compare or to print
    #    NOT COMPARED.
    # 4. EGRET'S PRICE IS ITS OWN AND WE WOULD DECIDE BY HERON. Both adapters
    #    read the knob, the measurement above is from one. The egret run
    #    (`LAYOUT_ADAPTER=docling-egret`, other knobs the same, 2026-08-29)
    #    covers the FIRST 150 pages, with heron beside it on THE SAME 150 --
    #    otherwise incomparable:
    #                            egret off -> full    heron off -> full
    #       boxes                  4145 -> 3025         4387 -> 3044
    #       duplicates IoU>=0.9     766 -> 3            1008 -> 3
    #       found of 313            190 -> 159           201 -> 156
    #       meaning whole of 313    155 -> 131           154 -> 121
    #       merged                   65 -> 86             57 -> 87
    #       ink outside boxes      22.8% -> 26.8%       24.3% -> 24.5%
    #       torn of 312              32 -> 36             38 -> 41
    #    In ink egret pays incomparably more, +4.0 points against +0.2 on THE
    #    SAME pages; by merging it loses less, -31 found against -45. And a
    #    quarter of the bench is not the bench: heron's share outside boxes
    #    grows 1.7 points over all 600 pages and 0.2 over this quarter. Firm
    #    only: the knob's second reader has a DIFFERENT price, and deciding for
    #    it by heron's numbers is dishonest.
    # FOR `full`, once the consumer is the pipeline and not the bench: 4435
    # duplicate pairs against 19, and 23.0 VLM requests per page against 14.6
    # -- money for reading, nearly double. A request is a non-artefact box and
    # `books feed` counts exactly as many; but that is an AVERAGE over 600
    # pages -- on the first ten `books feed` counted 59.7 and 47.4 per page, so
    # a handful of pages says nothing about the price of reading. Revisit the
    # default when the second level shows by a number what it does with a
    # collapsed wrapper.
    Knob("DOCLING_PIPELINE", "off",
         "the docling vendor pipeline over the boxes: off | post (its "
         "postprocessing) | full (that plus reading-order RULES, not a "
         "model). Read by the docling and docling-egret adapters; "
         "indigestible to the rest. The numbers beside this knob were "
         "taken on HERON -- egret has a price of its own, measured "
         "separately and different"),
    Knob("ASSEMBLY_ORDER", "ours",
         "what assembles the book when the model has NO reading rank of "
         "its own: ours (our rule, top to bottom and left to right) | "
         "docling (reading_order_rb -- 740 lines of vendor RULES, not a "
         "model; needs the docling package, +54 MB). Read by plus-L, "
         "heron, egret and yolox; PP-DocLayoutV2 and V3 have a rank of "
         "their OWN and this knob does not touch them at all. Measured on "
         "the 600 pages of the golden bench, THE SAME V2 boxes permuted "
         "three ways: our rule 2471 extra jumps, the model's own rank "
         "501, the docling rules 439. Ours is worse than both STEADILY -- "
         "over 16 sweep points the limits are 3.02..7.04 against "
         "0.23..1.73 and 0.28..1.57, not overlapping at all. And docling "
         "against the V2 rank the instrument does NOT tell apart: the "
         "pair is inverted, difference 0.13 against a ruler span of 4.02 "
         "-- which is why V2 keeps its own rank. The default is ours and "
         "not the best by number for exactly one reason: docling is a "
         "package, and `books detect --adapter yolox` must not fall on a "
         "fresh environment over a sorting rule"),
    # `PADDLE_PDX_MODEL_SOURCE` WAS REMOVED FROM THE REGISTRY, not marked debt.
    # Its only consumer was an `export` in `models/paddleocr_vl/run.sh`, left
    # from the era when layout was computed ON THE CARD and paddlex pulled
    # weights there; detection now happens at home and the box receives a ready
    # `detect/` directory. Debt is the wrong mark for it: debt is "declared,
    # consumer not there YET", and here the consumer EXISTED and vanished with
    # the work. Caught by `audit()`, not by a human.

    # --- artefact crops: both values default to "as the model saw it" ---
    # Any other value would be chosen by us and not measured -- even though at
    # 144 dpi a dense table gives 6-7 dots per glyph height and the second
    # level will fail on such a crop. The bench will set it.
    Knob("CROP_DPI", "",
         "crop sharpness. Empty = the scan's OWN resolution (as much as "
         "the file holds and not a dot more), and if that cannot be "
         "determined -- as detection had it. Here stood 'empty = as "
         "PAGE_DPI', wrong on both counts; a knob's text rides into "
         "run.json, so the snapshot described it falsely. Read by "
         "doc/crop.py and doc/feed.py; `books read` does NOT read it -- "
         "there the model's window decides the resolution"),
    # Zero is a VALUE: the pipeline cuts exactly along the box
    # (layout_unclip_ratio [1.0, 1.0]), and any non-zero margin edits the
    # model's box.
    Knob("CROP_MARGIN", "0",
         "margin around the box when cropping, in box fractions"),

    # --- VLM feed: two hypotheses, neither one checked --------------------
    # `crop` -- one request per text block, as the pipeline does by default
    # (measured: 409 requests over 25 pages, sixteen per page). `masked_page`
    # -- one request per page with artefacts masked out: sixteen times fewer
    # calls and the connected text whole.
    #
    # The default is `crop` not because it is better but because it is the
    # model's behaviour as it is, while `masked_page` is our invention. Known
    # AGAINST it: a blank white sheet yields five different Chinese tables in
    # five attempts; an isolated column read MORE correctly than a whole page;
    # the 4096-token answer ceiling against a longest single block of 8207
    # characters. None of the three was taken on a whole masked page -- hence a
    # knob and not a decision.
    Knob("VLM_INPUT", "crop", "what to feed the VLM: crop | masked_page"),
    # Not a constant: white is the least neutral option there is, and it was on
    # blank white that the model invented tables.
    Knob("MASK_FILL", "white",
         "hole fill under masked_page: white|gray|black"),

    # --- book, rental and ledger: not about parsing, about repeatability ---
    Knob("HTML_MATH", "inline",
         "how formulas are drawn in the book: inline (MathJax INSIDE the "
         "book, +2.3 MB to the file) | local (as a neighbouring "
         "tex-svg.js) | cdn (pulled from the network on every open) | off "
         "(raw LaTeX). The default is `inline`, and it was paid for like "
         "this: with `local` the browser silently DOES NOT LOAD the "
         "neighbouring script when the book is opened over a network path "
         "(\\\\wsl.localhost\\... from Windows) -- Chromium cuts the local "
         "file off, the console says nothing, and the book looks built "
         "without formulas. An embedded script knows no such trouble. The "
         "measurement this knob was made for: «Технология огнеупоров» "
         "holds 2260 formulas among 6080 read blocks, and without "
         "rendering the reader sees "
         "\\[\\mathrm{Al}_{2}\\mathrm{O}_{3}\\] instead of a formula"),
    Knob("HTML_IMAGES", "inline",
         "how the book carries the cut-out artefacts: inline (data: links "
         "INSIDE the html; the file is self-contained and opens by any "
         "path) | linked (links to assets/blocks/*.png). The PNGs are put "
         "into assets/blocks in BOTH cases -- edits, measurements and the "
         "second level need them, not reading alone. The price of inline "
         "on «Технология огнеупоров»: 488 crops, 11.2 MB on disk -> "
         "14.9 MB in base64, the book 2.3 -> ~19 MB. The default is "
         "`inline` for the same reason as HTML_MATH: a book gets opened "
         "over a network path, and then neighbouring files fail to load "
         "in silence"),
    Knob("HTML_REPEATS", "hide",
         "what to do with a PROVEN repeat inside a page: hide (not shown "
         "to the reader; the markup stays, only the display is hidden) | "
         "show (show everything, hiding nothing). The proof is one: the "
         "same text belongs to a block that STAYS in the book; compared "
         "at the latex step, whose measurement is in `text.NORM_STEPS`. "
         "On «Технология огнеупоров» 728 of 1935 nested blocks are "
         "hidden, the share of false ones among them 11.7 % by the worst "
         "background. THE KNOB IS NOT HERE FOR BEAUTY: it is the only "
         "build operation that TAKES text off the reader's eyes, and it "
         "must have a switch -- the cost of an error is asymmetric here, "
         "a false hiding carries words away while a missed repeat leaves "
         "one line too many"),
    Knob("MIN_LINK_MBPS", "2.0",
         "the link threshold a machine is rejected by, Mbps, measured TO "
         "US. It separates a working machine from a broken one, not a "
         "fast one from a slow one: two orders of magnitude lie between "
         "them (7 against 0.06). THIS NUMBER IS NOT DERIVED FROM THE "
         "WORK, and that has to be known before blaming the market. A "
         "`vl-read` job of 20 pages weighs 872 KB: at 0.34 Mbps it "
         "travels in 20 s, at 0.062 (that same broken machine from the "
         "probe's docstring) in 112 s. So for the task ITSELF the "
         "threshold of 2.0 is tenfold excessive, and by it machines are "
         "rejected for good. Measured 3 September 2026: our own link over "
         "HTTP 4.6 Mbps, while a single ssh stream to the rented machine "
         "gave 0.34, and it went onto the eternal blacklist. Loosening "
         "the threshold knowingly is exactly what it was put in the "
         "registry for; loosening it, take the number FROM THE JOB SIZE "
         "and not from taste, and remember that below the threshold a "
         "machine returns its result slowly too"),
    # The commit we computed with, FOR A MACHINE THAT HAS NO GIT. Measured: the
    # `vast-base` image carries no git (both layers unpacked), the box root
    # `/root/job` holds no repository, and `stamp.commit()` honestly returns
    # `None`. So the one run all this was written for -- the paid one -- would
    # be the one without a record of which code computed it, while `books
    # replay --check` returned 0, an empty field counting as a value. The job
    # builder sets the knob from its own `stamp.commit()`.
    Knob("BOOKSMITH_COMMIT", "",
         "the commit for a machine without git; empty = ask git in place"),
    Knob("BOOKSMITH_LEDGER", "",
         "where to write the run journal; empty = runs/ledger.jsonl. The "
         "machine blacklist lives beside the journal"),
    # --- VLM feed, continued ------------------------------------------------
    Knob("FEED_DPI", "",
         "resolution of the page going to the VLM; empty = as PAGE_DPI"),

    # --- synthetic bench ----------------------------------------------------
    # Seed and ageing profile decide which pages come out, hence decide the
    # model's answer: measured, a CLEAN page has no `table` box at all and an
    # aged one grows one. A bench without these two in the snapshot is not
    # reproducible.
    Knob("SYNTH_SEED", "1", "seed of the synthetic bench"),
    Knob("SYNTH_AGING", "old",
         "bench ageing profile: clean|scan|old|decayed"),

    # --- SECOND LEVEL: reading block content --------------------------------
    # The same cut as in `read/__init__.py`: what we ask is a property of the
    # MODEL, how we deliver it a property of the TRANSPORT, and the knobs are
    # split along it.
    Knob("VLM_READER", "paddleocr-vl",
         "which READING adapter to call; the list is read/run.py:READERS. "
         "It decides which prompt asks about which label, and in what "
         "shape the answer arrives"),
    Knob("VLM_TRANSPORT", "http",
         "how the question is delivered; the list is read/http.py:build. "
         "Rental is NOT a third transport: on a rented card the same http "
         "looks at 127.0.0.1, where run.sh raised vLLM"),
    # AN EMPTY DEFAULT HERE DROPS THE RUN, and that sets this knob apart. Empty
    # defaults number eight (`VL_MODEL_DIR`, `YOLOX_WEIGHTS`,
    # `LAYOUT_MODEL_DIR`, `CROP_DPI`, `BOOKSMITH_COMMIT`, `BOOKSMITH_LEDGER`,
    # `FEED_DPI` and this one); here stood "the only such knob", wrong, and
    # `books replay --check` prints the same 8. It is special not by being
    # empty but by the emptiness NOT being passed on: a silent
    # `http://127.0.0.1:8118/v1` would have a run at home knocking at nothing
    # and calling a refused connection a silence of the model -- two different
    # zeros.
    Knob("VLM_ENDPOINT", "",
         "address of an OpenAI-compatible service, /v1 included; no "
         "default"),
    # 4096 is not our number: the stock PaddleOCR-VL pipeline sets it, lowering
    # the model's native 8192. What makes it a knob and not a constant: the
    # longest SINGLE text block in our books is 8207
    # characters, twice the ceiling, and truncation in this model looks like
    # looping, after which `otsl_pad_to_sqr_v2` silently shortens long rows --
    # a torn table comes back plausible. Only the `finish` field tells them
    # apart, and a run is obliged to print it.
    Knob("VLM_MAX_TOKENS", "4096", "ceiling of an answer, in tokens"),
    Knob("VLM_TIMEOUT_S", "120", "how long to wait for one answer, s"),
    # A 200 is never retried whatever it carries: re-asking after an answer
    # repairs the model, and the project rule forbids it -- here the ban is
    # expressed in code (`read/http.py`). The number is about broken links, of
    # which a rented machine has plenty: the ledger remembers 0.06 Mbps.
    Knob("VLM_RETRIES", "2",
         "how many times to repeat a DELIVERY REFUSAL (not an answer)"),
    # vLLM batches on its own and a single stream leaves the card nearly idle;
    # but any number above one makes the order of ANSWERS non-deterministic, so
    # it is declared and rides into the snapshot, and pages are written by
    # anchor rather than by arrival.
    Knob("VLM_CONCURRENCY", "4",
         "how many requests to keep in flight at once"),

    # --- generation ---
    Knob("VLM_TEMPERATURE", "0", "VLM temperature; >0 makes the parse "
                                 "unrepeatable on purpose"),
    # BOTH ARE DECLARED THOUGH AT temperature=0 THEY CHANGE NOTHING. Not
    # pedantry: `books replay --check` demands the snapshot's "generation"
    # field be FILLED and not empty, and it is right -- "top_p was not set" and
    # "top_p was not looked at" are different runs. The moment the temperature
    # is raised (self-consistency of three reads at 0.4 caught invention: 217
    # matching cells of 270, and the two worst pages came first by
    # instability), both start deciding the answer, with nowhere to recover
    # them from afterwards.
    Knob("VLM_TOP_P", "1.0", "probability cutoff; 1.0 = cut nothing"),
    Knob("VLM_SEED", "0", "generation seed; decides at temperature > 0"),
    Knob("PASSES", "1",
         "how many reads; summing up is the runner's job, not the "
         "model's", debt=True),

    # --- observation, NOT intervention ---
    # They go to their own file and never touch the text. This same knob used
    # to insert `⚠` and `<mark>` straight into the markup, i.e. corrected the
    # model's output. Recognised text is now untouchable, and everything
    # observed lives alongside, tied to a block by its number.
    Knob("LOGPROBS", "1", "record token probabilities beside the page",
         debt=True),

    # --- shell ---
    Knob("PORT", "8118", "port of the vLLM service on the machine"),
    # A page counts as done by the artefact it was paid for, not by any trace
    # carrying its number. The old implementation took ANY file with a numeric
    # name: a page is written by two calls and the first can fail (measured on
    # the "Spravochnik": 3 pages of 760 left without `.md` while the `.json`
    # lived), `--resume` never recomputed such a page, and `run.json` showed
    # the full count as if all were there. In the book the hole shows only as a
    # paragraph ending mid-word.
    Knob("RESUME", "1", "whether to continue an interrupted run"),
    # The default is "0" and not "": that is what `run.sh` does (`${X:-0}`),
    # and while the right-hand side lives there as a second copy the registry
    # has to say the same. It used to be "", so the snapshot would record ""
    # where the run saw "0" -- the `VL_MODEL_DIR` disease of this file's
    # header, only quieter. Zero here is a VALUE: flashinfer compiles its
    # sampler on the spot and fails to build (incompatible cccl headers), so it
    # is off deliberately.
    Knob("VLLM_USE_FLASHINFER_SAMPLER", "0", "flashinfer sampler in vLLM"),
)
KNOB = {k.name: k for k in KNOBS}


def knob(name):
    """A knob's value: from the environment, else the registry default."""
    try:
        k = KNOB[name]
    except KeyError:
        raise KeyError(f"knob {name} is not declared in KNOBS: declare it "
                       f"there instead of reading the environment past "
                       f"the registry") from None
    v = os.environ.get(k.name)
    return k.default if v is None else v


def number(name, *, kind=float, negative=False):
    """A knob's value AS A NUMBER, refusing what a number should not be.

    `float()` accepts `nan` and `inf`, and `nan` compares False with
    EVERYTHING -- so a mistyped knob does not fail, it makes every comparison
    that guards it silently false. Swept across the tree, six knobs took it and
    carried it into a run: `CROP_DPI` and `CROP_MARGIN` past guards that refuse
    zero and negatives; `VLM_TEMPERATURE` and `VLM_TOP_P` onto the PAID path;
    `VLM_TIMEOUT_S` into urllib; `LAYOUT_SCORE_THRESHOLD` into every box
    comparison. Worst of them, `PAGE_DPI=nan` built the golden bench to
    completion: truth coordinates in one system, pdf geometry in pymupdf's
    default letter page, `nan` in the manifest, and not a word said.

    That is the shape this project keeps a rule about -- a zero from a check
    against a zero from not understanding -- so the reading is in ONE place
    and refuses out loud. Zero is allowed here and refused by the knobs that
    care: `CROP_DPI` has its own reason, and it says it.
    """
    raw = knob(name)
    try:
        v = kind(raw)
    except (TypeError, ValueError):
        raise SystemExit(
            f"{name}={raw!r} is not a number: {kind.__name__} expected. A "
            f"knob that decides a run may not be a typo") from None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise SystemExit(
            f"{name}={raw!r}: not a finite number. `nan` compares False with "
            f"everything, so every guard around this knob would quietly stop "
            f"holding -- and the run would finish and say nothing")
    if f < 0 and not negative:
        raise SystemExit(f"{name}={raw!r}: negative, and this knob is not")
    return v


def snapshot():
    """Every knob at once: what stood, what the default was, was it set.

    The "debt" field was added, not substituted for anything: snapshot
    consumers read "value" and ignore the extra key. In exchange any run's
    `run.json` now YIELDS the count of dead knobs in it -- before, that could
    only be subtracted from this file's header prose, where it went off.

    "Debt" and the "read by" field `detect.py` adds on top are DIFFERENT
    questions. "Read by" is about THIS run: nobody reads
    `LAYOUT_TABLE_THRESHOLD` in a heron run, yet the knob is alive --
    `doclayout.py` reads it. "Debt" is about the whole tree: NOBODY has a
    consumer. Merging them would declare dead everything today's adapter did
    not touch.
    """
    return {k.name: {"value": knob(k.name), "default": k.default,
                     "set_externally": k.name in os.environ, "what": k.what,
                     "debt": k.debt}
            for k in KNOBS}


def snapshot_with_readers(roles):
    """The knob snapshot, each knob saying WHO READS IT in this run.

    IT LIVES HERE BECAUSE THERE ARE TWO SNAPPERS. Private to `detect.py` once;
    the second level needed it in `read/run.py`, and that second edition came
    out A DIFFERENT SHAPE -- three nested buckets instead of a flat map.
    `books replay --check` rejected it silently: it looks for
    `knobs/NAME/value` and on the nested one printed "no knobs/VLM_SEED/value",
    declaring INCOMPLETE a snapshot that held everything. No third edition.

    Knobs are NOT dropped -- a complete snapshot is a condition of
    repeatability. But without the mark it reads as if every value were in
    force, while a heron run has exactly three. Hence an owner and a flag
    beside the value: the string for a human, the flag for a machine.
    """
    snap = snapshot()
    for name, rec in snap.items():
        who = roles.get(name)
        rec["read_by"] = who or "NOBODY IN THIS RUN"
        rec["for_this_run"] = who is not None
    return snap


def debts():
    """Knobs declared debt: no consumer, and none due yet."""
    return tuple(k.name for k in KNOBS if k.debt)


def names():
    return tuple(k.name for k in KNOBS)


def passthrough():
    """What to pass to the rented machine: only what the OPERATOR set.

    Defaults are not substituted -- they have one place of residence, this
    file. The list is built from the registry rather than typed by hand:
    hand-typed it had already diverged, holding 13 names of 17, with four knobs
    deciding the choice of weights never reaching the machine at all.
    """
    return {n: os.environ[n] for n in names() if n in os.environ}


# The source directory, `src/booksmith`. From here rather than from the
# process's working directory -- otherwise `readers()` run from another cwd
# would silently find zero consumers for every knob, and `audit()` would howl
# at the whole registry.
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def readers(root=None):
    """Who REALLY reads each knob: name -> tuple of files, by walking the tree.

    Counted, not remembered: the header's prose list named 11 live consumers
    when there were 16, and missed five knobs read by every `books detect`.
    Numbers in comments obey the rule numbers in the ledger do: a value, not a
    word, and a value counted.

    WHAT IT SEES AND WHAT IT DOES NOT. In `.py` the two direct forms,
    `knob("NAME")` and `number("NAME")`; a read through a variable is
    not found, the knob looks dead, and `audit()` howls a false alarm. The bias
    is deliberate: a false alarm costs a minute, a silent "all is well" cost
    the project `VL_MODEL_DIR`. In `.sh` it searches `$NAME` and `${NAME}` --
    exactly how the shell on the rented machine takes a knob, past `knob()` and
    past any `KeyError`.

    This file is excluded from the walk: it names every name by construction
    and would otherwise consume every knob.

    The adapters' `knobs_read()` declarations are not checked here, but since
    2026-08-29 `tests/test_knobs.py` checks them, and the cost is there too: a
    hand-typed list ("verified by grep over the file" in doclayout,
    docling_heron, yolox) diverges from the tree silently, and the snapshot
    then calls a value in force that the run never saw.
    """
    root = root or SRC
    me = os.path.abspath(__file__)
    found = {k.name: [] for k in KNOBS}
    sh = {n: re.compile(r"\$\{?" + re.escape(n) + r"\b") for n in found}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(files):
            if not fn.endswith((".py", ".sh")):
                continue
            path = os.path.join(dirpath, fn)
            if os.path.abspath(path) == me:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            rel = os.path.relpath(path, root)
            py = fn.endswith(".py")
            for name in found:
                # BOTH SPELLINGS. `number("NAME")` is the reader for numeric
                # knobs, and this detector knew only `knob("NAME")` -- so the
                # moment six knobs moved onto it, nine of them looked DEAD and
                # `audit()` howled about a registry that had not changed. A
                # detector that knows one of two ways to read is the same
                # defect it exists to catch, one level up.
                hit = (any(f'{fn_}("{name}")' in text
                           or f"{fn_}('{name}')" in text
                           or f'{fn_}("{name}",' in text
                           or f"{fn_}('{name}'," in text
                           for fn_ in ("knob", "number"))
                       if py else sh[name].search(text) is not None)
                if hit:
                    found[name].append(rel)
    return {n: tuple(v) for n, v in found.items()}


def audit(root=None):
    """Declared debt against what the tree holds. Empty means they agree.

    Two troubles, both quiet. A knob started being read and `debt=True` was not
    taken off it -- the registry lies that the setting is dead and people stop
    passing it through. Or the last consumer was deleted with its code while
    the knob stayed standing as alive -- exactly how the header accumulated its
    five-name discrepancy, noticed only by proofreading.
    """
    who = readers(root)
    out = []
    for k in KNOBS:
        seen = who[k.name]
        if k.debt and seen:
            out.append(f"{k.name}: declared a debt (debt=True), and yet "
                       f"{', '.join(seen)} reads it -- drop the mark")
        if not k.debt and not seen:
            out.append(f"{k.name}: not one consumer found -- either it was "
                       f"lost together with its code, or set debt=True")
    return out
