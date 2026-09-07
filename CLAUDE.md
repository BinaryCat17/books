# booksmith

A pipeline that turns scans of technical books into **HTML**.

HTML is the one goal, and an intermediate one. Markdown is not a goal any more
-- its table markup is poorer than what has to survive. EPUB, FB2 and PDF are
not needed at all; the format builder is deleted. Reading on a screen, when it
is wanted, is made from the HTML and later.

**This file is the MAP.** It says where things are and what may not be done.
It deliberately holds almost no measurements: they used to live here and in
five other files at once. One figure -- the artifacts V2 finds on the golden
bench -- stood here twice, in the contour journal three times and in the
source six more. A second copy drifts, and it drifts silently.

## Where each kind of text lives

| you want | read |
|---|---|
| what a model is, what it costs, what it found, the verdict | `docs/models.md` |
| what cannot be measured yet, and the rules that outlive their code | `docs/limits.md` |
| how a contour number was obtained, and what the traps cost | `docs/contour-notes.md` |
| the same for reading | `docs/ocr-notes.md` |
| the same for renting a card | `docs/vast-notes.md` |
| what the deleted code knew, saved from it | `docs/lessons-from-deleted-code.md` |
| what a bench is and when it lied | `bench/README.md` |
| the price of a specific mistake | the comment beside the code that can repeat it |

The last row is not a joke and not laziness. A warning about `_sheet_trouble`
belongs in `src/booksmith/processing/assemble/html.py` because that is where
the next person will break it.
Prose far from its code goes stale; prose beside it gets read.

## The two levels

1. **Level one** walks the whole book and returns **contours**: boxes, labels,
   reading order. Not one character of text -- it is a layout detector, not a
   recogniser. HTML built from contours alone is a book in which EVERY block is
   a picture, text ones included.
2. **Level two** takes each extracted artifact **in isolation from its
   neighbours** and turns it into a block of HTML. Substitution goes one at a
   time, with a journal and an undo, so each one can be checked, rolled back
   and redone by another model without touching the book.

Text appears at level two: `books read` fills `content`, and only then does
`books html` print text blocks as markup and leave pictures for artifacts
alone. Their markup is placed by `books apply`.

The order of work is the reverse of the usual one: the bench and the
instruments first, the models second. Otherwise it becomes a third edition of
the same code, judged by the same eyes.

## Code

```
src/booksmith/
  core/        THE KERNEL, imports nothing above itself: page.py (Block, Page,
               KINDS: the on-disk format, one shape for truth and output),
               book.py (where a book's parts live), knobs.py (the registry),
               stamp.py (hash, commit, packages: the three quantities of
               repeatability), replay.py (is a snapshot complete), raster.py
               (page rendering and crop cutting; the only rendering seam on
               the read path), policy.py (label -> class, five vocabularies),
               order.py (THE ASSEMBLY ORDER, knob ASSEMBLY_ORDER), otsl.py
               (parsing the table markup, OUR code), textnorm.py (text
               normalisation before comparison), schema.py (key floors over
               the tracked files), config.py (.env), errors.py (Refusal rc 1,
               Unmeasurable rc 2), log.py (one log line)
  tree/        instruments over the tree itself: cyr.py (the Cyrillic
               ratchet), imports.py (the dependency rule, held by a test)
  remote/      renting and running ANYTHING on a rented machine. Knows nothing
               about PDF or OCR and must not -- otherwise the next task means
               rewriting the renting again. Four independent ways to kill a
               machine, including a dead-man's watch on the card itself; each
               was added after the previous one let money leak
  processing/  MODULE 1, one book stage by stage: extract/djvu.py (djvu ->
               PDF with spreads cut apart); layout/ (base.py the Detector
               contract, detect.py level one, adapters/ doclayout,
               docling, yolox -- all ONNX on the CPU --, rented/dots_ocr a
               layout VLM delivered to a rented card); read/ (LEVEL TWO,
               `books read`: __init__ the contract for reading a block,
               driver.py the book driver whose product is THE SAME
               pages/*.json detection makes with content and kind filled
               in, transports/openai_http.py delivery to any OpenAI-
               compatible address, readers/paddleocr_vl.py the one reader,
               rented/paddleocr_vl the job that raises vLLM on a card);
               assemble/ (html.py contours into HTML, swap.py and apply.py
               one picture replaced by markup at a time with an undo,
               mathjax/ shipped beside the book, knob HTML_MATH); assess/
               (ink.py the ink measurement -- will the meaning reach the
               second level; needs no truth)
  datasets/    MODULE 2, many books, truth, numbers: bench.py (Bench, Run:
               the one loader and the one identity check), metrics/ (base.py
               the contract -- Metric, Record, Scalar, the one battery loop;
               mutate.py the mutators the batteries share; contour.py boxes
               and order against truth; text.py characters and cells against
               truth; fitness.py the ink metric's battery and Record;
               assembly.py excess column jumps, needing no truth; snapshot.py
               is the run's snapshot complete), make/ (synth/ the synthetic bench with truth
               measured by ink -- draw.py the drawers, age.py the aging,
               truth.py the measured truth, books/ the six book kinds --,
               annopage.py the golden bench of 600 real pages, subset.py the
               distillate),
               look.py boxes drawn over the pages, table.py every metric on
               one run side by side, accept.py reports and records against
               bench/expected/
  cli.py       books <command>
tests/         collusions between files, own runner (there is no pytest in
               .venv): tests/run.py, and tests/run.py --slow --selfcheck for
               the mutations, ALL of which must be caught. DO NOT ASK THIS
               PROSE FOR THE NUMBERS -- ask the runner, it prints them on its
               last line
tools/         cyr.py (Cyrillic ratchet and the residue lock), anchors.py
               (do the battery's source patches and attribute swaps still
               land), acceptance.py, migrate_layout.py (the package move as a
               table), prose_only.py, keymap*.json, migrate_*.py -- the
               instruments and the record of the renames
```

## Commands

```
books doctor                 check everything BEFORE the money starts
books offers                 look at the market, renting nothing
books prepare book.djvu      djvu -> PDF, spreads cut apart
books ls | books down <id> | books reap
books ledger                 the run journal and the estimate from it
books replay --check out/    is the input snapshot complete

books detect book.pdf        LEVEL ONE: page contours, locally and free
books read book.detect/      LEVEL TWO: read the blocks with a model. PAID,
                             and the only command of the parse that spends
books html out/              readable HTML: text plus artifacts as pictures
books crop book.detect/      what `books read` would send, by its own path;
                             nothing sent
books apply out/             put the read markup into the book; the source
                             comes from its own snapshot, repeats are free.
                             --status, --anchor/--file, --undo, --from
books synth --book slovar    a synthetic book with exact truth
books annopage raw/annopage  the golden bench: real pages with truth
books subset                 the distillate: artifacts side by side
books score truth/ boxes/    contour metrics; --selfcheck runs the battery
books text truth/ pages/     the reading metric; --selfcheck too
books fitness book.pdf --detect …   will the meaning arrive: ink, not boxes
books overlay book.pdf …     truth and model disagreements over the pages
books bench all bench/<book>  every applicable metric on one run: one table,
                             one JSON under bench/results/
```

## Knobs

Every knob is declared in `src/booksmith/core/knobs.py`. Reading the
environment past the registry is a defect: a knob that is not in the registry
does not reach the snapshot, and the run becomes silently unrepeatable.

How many there are and who reads them, ask the registry, not this file:

    python -c "from booksmith.core import knobs; r = knobs.readers(); print(len(knobs.KNOBS), sum(1 for v in r.values() if v), len(knobs.debts()))"

Which detector `books detect` calls is decided by `LAYOUT_ADAPTER`
(`doclayout` | `docling` | `docling-egret` | `yolox`); inside the paddle
family the model is chosen by `LAYOUT_MODEL_NAME`, the YOLOX weights by
`YOLOX_WEIGHTS`. `DOCLING_PIPELINE` turns on the vendor pipeline over heron
and egret -- what it buys and what it costs is in `docs/models.md`.

## The rules that are not negotiable

Stated here in one line each; the measurement that bought each one is in
`docs/limits.md`.

* **Nobody repairs the model.** No merging boxes, no cutting across the
  gutter, no re-asking, no thresholds tuned by us. A patch does not improve
  the book -- it hides the defect from the measurement.
* **What was recognised is untouchable.** Everything observed lives beside the
  block and is tied to it by number.
* **A metric must be able to fail.** Feed it a broken input and watch the
  number fall, before believing it.
* **Log the quantity, not the word "done".**
* **Zero from a check and zero from not understanding are different zeros.**
* **A knob is declared in the registry.**
* **Words and structure may be repaired; numbers may only be flagged, never
  restored.**

## The book directory is self-sufficient

```
processed/<book>/
  book.html          ONE file at the root, referring to nothing outside:
                     MathJax and the crops are inlined
  assets/            the kitchen; a reader has no business here
    blocks/*.png       crops as files -- for edits, measurements, level two
    blocks.json        what was observed, beside the block, keyed by anchor
    run.json           the build snapshot
    swaps.json         the swap journal: a STACK per anchor, undo one step
    source/            WHAT THE BOOK WAS BUILT FROM: pages/, answers/,
                       run.json, read_with.json
```

`source/` exists because of a measurement, not for tidiness. Without it the
directory held everything needed to READ the book and not everything needed to
REBUILD it. With it, `books apply` with no arguments takes the source from
here rather than from an absolute path in the snapshot, and so survives the
book being moved to another machine.

**The only thing not inside is the source PDF**: crops are cut from it, and a
rebuild needs `raw/<book>.pdf`. Its path and sha256 are in `assets/run.json`;
reading the finished book does not need it.

## State

The two levels both work end to end. Level one is measured on two benches;
level two has run on a real book and cannot yet be measured for quality --
`docs/limits.md` says why, in three reasons, before any money is spent.

The project is being translated to English, keys of the on-disk format
included. What is left, by area, is printed by:

    python3 tools/cyr.py

Every area may fall and none may rise, and each carries a second number --
the Latin that arrived where the Cyrillic left -- because deleting a comment
moves the first number just as well as translating it does.
