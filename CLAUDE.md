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
belongs in `doc/html.py` because that is where the next person will break it.
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
  remote/      renting and running ANYTHING on a rented machine. Knows nothing
               about PDF or OCR and must not -- otherwise the next task means
               rewriting the renting again. Four independent ways to kill a
               machine, including a dead-man's watch on the card itself; each
               was added after the previous one let money leak
  models/      detection adapters, all ONNX on the CPU: base.py is the
               contract, doclayout.py (PP-DocLayout*), docling_heron.py
               (heron and egret), yolox_layout.py; paddleocr_vl/ and dots_ocr/
               deliver a VLM to a rented machine
  books/       bench books: reference, dictionary, mathematics, atlas,
               catalogue, article collection -- each a different format
  doc/         contours into HTML: crop, feed, html; swap and apply are level
               two -- one picture replaced by markup at a time, with an undo;
               mathjax/ ships MathJax beside the book, knob `HTML_MATH`
  read/        LEVEL TWO, `books read`: the contract for reading a block
               (__init__), transport to any OpenAI-compatible address (http),
               the book driver (run). Its product is THE SAME `pages/*.json`
               detection makes, with `content` and `kind` filled in
  otsl.py      parsing the table markup reading models answer with. OUR code,
               not the model's: "the model said nothing", "our parse did not
               come together" and "the characters are wrong" must be three
               different answers
  run/         the knob registry, the input snapshot, three quantities of
               repeatability (stamp: file hash, commit, packages)
  schema.py    THE ON-DISK FORMAT, declared once, with a measured floor under
               every key. The names come from here and the counts off the
               disk, which is the only shape that fails in both directions
  cyr.py       the Cyrillic ratchet: how much is left of the translation, by
               area, and how much Latin arrived in its place
  acceptance.py  seven reports compared line by line against `bench/expected/`
  policy.py    label -> class: artifact | text | furniture. Each detector has
               its own vocabulary, five of them
  order.py     THE BOOK ASSEMBLY ORDER, one rule for the project. Knob
               `ASSEMBLY_ORDER`. Applies only to models with no rank of their
               own; V2 and V3 have one
  detect.py    level one: page contours, locally and free
  synth.py     the synthetic bench: pages with truth measured by ink
  annopage.py  the golden bench: 600 real pages, truth by librarians
  subset.py    the distillate: pages where artifacts stand side by side
  metrics.py   contour metrics and the mutation battery
  fitness.py   fitness of the output for the pipeline, BY INK; needs no truth
  text.py      the READING metric: characters against the bench truth, CER/WER
               and the table grid by cell address; its own damage battery
  overlay.py   boxes over the pages -- to look with your own eyes
  djvu.py      djvu -> PDF with spreads cut apart
  config.py    secrets from .env and paths
  cli.py       books <command>
tests/         collusions between files, own runner (there is no pytest in
               .venv): tests/run.py, and tests/run.py --slow --selfcheck for
               the mutations, ALL of which must be caught. DO NOT ASK THIS
               PROSE FOR THE NUMBERS -- ask the runner, it prints them on its
               last line
tools/         cyr.py, acceptance.py, prose_only.py, keymap*.json,
               migrate_*.py -- the instruments and the record of the rename
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
books feed out/              what would go to the VLM, without asking it
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
```

## Knobs

Every knob is declared in `src/booksmith/run/knobs.py`. Reading the
environment past the registry is a defect: a knob that is not in the registry
does not reach the snapshot, and the run becomes silently unrepeatable.

How many there are and who reads them, ask the registry, not this file:

    python -c "from booksmith.run import knobs; r = knobs.readers(); print(len(knobs.KNOBS), sum(1 for v in r.values() if v), len(knobs.debts()))"

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
