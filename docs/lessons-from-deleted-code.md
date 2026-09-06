# What the deleted code knew

The clean slate took out 6.6k lines. With them would have gone measurements,
crash post-mortems and rejected hypotheses paid for in money and fallen
machines. Git history does not count as keeping: nobody reads it.

Only what does **not depend on the deleted Mistral OCR reference** is here, all
of it verified word for word against the text of the deleted files. Table
quality figures ("22 of 22", "79% of value rows") are not here: they are void,
see the preface of `docs/ocr-notes.md`.

---

## Acceptance must be able to fail, and mutations are how you prove it

From `tests/mutants.py`:

> "A test that falls on no mutation is background, not a check. This project
> has been there: **the `≠` mark stood on 416 tables of 448 and meant
> nothing**."

How it worked: every mutation is an edit made to the code and rolled back
after, with a list beside it of the suites that **must** go red from it; return
1 if any mutation is caught by no suite. Plus `harness.need()`: a check whose
function is missing from the tree is skipped **loudly** -- a silent skip is the
background. The same file held a measured defect of the instrument itself: the
ruler `<[^>]+>` instead of `<[^<>]*>` understated the word count by **9.0%**
(84 069 against 92 405), because a bare angle bracket arrives from mathematics
like `$1 < K$`.

**What follows for the new bench.** A contour metric is founded together with
its mutation table and its own exit code, not after. "A metric must be able to
fail" without a mutation registry is a promise, not an instrument.

## The chain of passes: five money mistakes

From the deleted `cli.py`, functions `_multipass` and `_drop_machine`. The
machinery (`keep_until`, `keep_usd`) survived in `remote/runner.py`, the caller
did not: the cure is left, the disease erased, and the chain will be written
again.

* **Budget and deadline belong to the whole chain, not to a pass.** "`--passes
  3 --timeout 90` meant not an hour and a half **but four and a half**: three
  independent watchdogs of 90 minutes each. The money ceiling multiplied by
  three the same way." An operator who typed "no more than a dollar and no
  longer than an hour" bought three dollars and three hours -- silently.
* **A break in the middle of the chain.** "A break on the second pass left the
  machine alive until the dead man's watch, and `--timeout 90 --budget 1.00`
  turned into **189 minutes of billing**."
* **The machine number was taken after `return rc`.** A failed first pass left
  `iid` empty, the kill quietly did nothing, and the machine went on with
  `--keep` and lived to the dead man's watch, "burning the whole declared
  budget without a single page of result".
* **`iid or …` did not pick up a replacement.** If the first machine died and a
  second was taken, the kill went to a machine that no longer existed; the next
  pass went with `--reuse` onto a corpse and took a third, while the live
  second was left abandoned and unaccounted.
* **`cost is None` is not "no money spent".** Otherwise the money half of the
  limiter switched itself off entirely and silently.

Plus the threshold `MIN_PASS_MIN`: a minute is not enough even for connecting
and raising the server (11 s + 66 s on a repeat pass, one and a half to fifteen
minutes from cold).

## How to tell that reading has degenerated

From `merge.py`. Looping is the universal failure of an autoregressive VLM: it
does not depend on the reference and will come back with any model. Three
signs:
1. an exact repeat of 30-grams;
2. a repeat with **link drift** (digits collapsed to `#`) -- this catches
   `2024年10月15日 2024年10月16日 …`, 4 095 characters of Chinese dates on a
   title page where the exact repeater sees only 1 064;
3. an arithmetic progression.

> "Measured on six books, **9 783 pages of three passes: 125 firings, of them
> 0 false** -- every one checked by eye, seven of them against the scan too."

**Rejected by measurement:** "gzip compressibility was measured and NOT
included: every page with `gz <= 0.10` is caught by the repeat detector, and it
adds not one of its own." This is the first thing that will be proposed again.

## Comparing two cells: where the normalisation boundary runs

From `merge.py`, measured on six books, **32 634 cells** of the base. Any
comparison needs it -- two readings against each other, or a reading against
truth.

| step | removed | harm |
|---|---|---|
| NFKC and whitespace | 127 | 0 |
| case | 90 | 0 |
| dash / hyphen / minus | 376 | 0 |
| decimal comma | 42 | 0 |
| trailing punctuation | 147 | 0 |
| **-- the boundary --** | | |
| leading punctuation | 139 | **4** (`.850` == `850`) |
| all punctuation | 504 | **108** (`6—2` == `6,2`) |

**Rejected by measurement:** the step "Cyrillic/Latin lookalikes". Substituting
a lookalike in this corpus IS the recognition error itself, not a spelling
variant: on the scan "Х10Л6", in the book "X10A6". With the step -- 14 finds of
29, lift **2.70**; without it -- 16 of 29, lift **3.06**.

## Readiness is counted by the artefact, not by the trace

From `jobs/paddleocr/entrypoint.py`, about `--resume`:

> "A page is written by two calls, `save_to_markdown` then `save_to_json`, and
> each is wrapped in its own `try`. The first can fall (measured on the
> Handbook: **3 pages of 760 were left without `.md` while the `.json`
> lived**). The old count took **any** file with a numeric name and declared
> the page ready; `--resume` never recomputed it, and `run.json` showed the
> full page count as though everything were in place. In the book the hole
> shows only as a paragraph ending mid-word."

The knob `RESUME` stayed in the registry; the knowledge is here.

## The knob registry does not rest on `KeyError`

From `tests/test_knobs_registry.py`:

> "The check **parses the source as a tree** rather than running the code: the
> branch `if os.environ.get("PROBE") == "1"` never executes on a stub… and
> `export NEW=…` in run.sh -- **that is how `VL_MODEL_DIR` was caught last
> time**: the shell sets the knob, it is invisible in entrypoint.py, and it
> decides which weights vLLM will raise."

The catcher has not been restored. `run/knobs.py` says so honestly in its
header.

## Memory when building formats

From `convert.py` and `tests/test_convert_stand.py`. The target is HTML now, so
pandoc and browser typesetting will return -- and the memory ceiling of an
external converter will otherwise have to be found by crashing a machine one
more time.

> "`-native_divs`. The most expensive one. Measured on Biochemistry (2.5 MB of
> markup, 1590 divs): with `native_divs` -- **peak RSS 4.7 GB and 129 s**,
> without it -- **279 MB and 6.5 s**. That, **and not WeasyPrint alone**, was
> what dropped the machine: six books in a row take **10.9 GB**, and the
> machine has **7.9**."

A correction to the walking version: WSL was dropped by **pandoc with
`native_divs`**, not by WeasyPrint alone -- the culprit is named by the deleted
file itself. Two silent losses from the same place:
* `-raw_tex`: "one unclosed brace in a cell is enough to eat half the book" --
  184 tables against 470, 237 image tags against 1434;
* `-markdown_in_html_blocks`: the cell `(a) .004"` opens an `<ol>` inside a
  `<td>` and swallows the rest of the table -- that is how 2 tables of 41 went
  missing.

The result of the fixes: epub files that do not parse as XML were **147 of
223** across six books, and became **6 of 263**.

## Zero from a check and zero from incomprehension are different zeros

From `docs/plan-fixes.md` and `structure.py`.

> "`report.md` prints 'References to figures in the text 0, images 103' as a
> meaningful diagnosis, although the label `figure_title` gave 66 blocks -- the
> counters are hard-wired to the English `Fig\.`."

> "A chapter number can be Roman… of four books parsed at once, all four had
> chapters and not one was recognised. The report honestly wrote 'chapters 0'
> -- and that read as 'the book has no chapters', not as 'I did not recognise
> them'."

Of the same kind: Feynman numbers his sections with `§`, so "section order
violations 0" is not the result of a check but the absence of one. And the
converse: one phrase `chapter 40` in a one-chapter book drew thirty-eight
unassembled chapters into the journal.

## A check has three outcomes, not two

From `docs/ocr-notes.md`, moved here when that file was cleaned. The rule about
pipeline steps ("print the quantity, not 'done'") gains a second one about
checks themselves, and it surfaced three times in one morning.

* **Rejecting machines by channel went silent at zero.** `probe()` returns 0.0
  on timeout, and both message branches tested `if link` and `elif link` -- at
  zero both are false. In the journal: ssh ready in five seconds, then nothing,
  then "DESTROYED" half a minute later. Ten such attempts in a row looked like
  "a bad market"; I blamed the market first, then my own regression, and both
  guesses were wrong.
* **The measurement of our own channel returned zero and the threshold stayed
  as it was.** First the 3 MB probe did not fit in its deadline -- that is, the
  insurance against a narrow channel was broken by a narrow channel. Then
  Cloudflare answered 403 without a `User-Agent` header. In both cases
  everything looked as if it worked.
* **A machine with a broken card passed selection.** `mark_bad` knew only about
  the channel, and a card falling with `CUDA unknown error` had a splendid
  network. Such a machine would come back again and again.

The rule: any check has three outcomes -- good, bad, and **could not check**.
The third must be loud and must never silently mean "good". Here it meant
exactly that three times. From the other side, a fuse that is too tight also
costs money: a five-minute ceiling per attempt rejected two good machines in a
row, vast counting a container as started before ssh begins listening while
`Connection refused` drags on for four and a half minutes. Four different ways
of getting an unusable machine in one hour -- a narrow channel, a slow ssh, a
dead card, and our own wrong threshold.

## The third witness: the PDF text layer

The prescription to check numbers against the PDF's own text layer went out of
`docs/ocr-notes.md` with the rest of the void material, but the technique is
recorded here: the extraction code (`engines/pdf_layer.py`, 375 lines) is
deleted, and the layer was the one witness that is **neither Mistral nor costs
money**. What was non-trivial in it: reading two columns in the right order,
the gutter band `BAND = 10.0`, `WIDE_FRAC = 0.49` for headings across columns,
margins of 30/45 pt at a page width of ~506 pt, joining paragraphs across a
page break, cutting illustrations out of an MRC scan.

## A detection threshold is set for all classes at once

A trap of somebody else's library, independent of the reference: given a
dictionary of thresholds, `postprocess` takes 0.5 for the classes not listed --
so a dictionary with one class silently worsens all the others. The threshold
was set for **all 25 classes explicitly**.

## Small things, expensive to find twice

* **The filename limit is 255 BYTES, not characters.** A Cyrillic title of 120
  characters is 240 bytes; with the extension tail, 262. "This fell over after
  the passes had already been paid for."
* **Reserved names.** `report.pdf` produced `report.md`, and the report was
  written over the assembled book -- with a zero exit code.
* **`splitext` bites the tail off a book.**
  `Фейнмановские_лекции_по_физике._1` is a legal name, and `._1` leaves as an
  extension.
* **A measurement without a run name can be neither confirmed nor refuted**:
  both sides get their own number and both are right.
* **A date beside a number.** The main error of the previous plan edition fell
  to one comparison: the book's build time against the commit's. A measurement
  without a date says nothing about whether it applies to what is on disk.
* **Edited `cli.py` -- then run `books`.** Checking the consequences of an edit
  instead of the edit itself is exactly how the CLI was broken.

## Rejected by measurement, on the renting side

* **"Merge the passes into one remote job".** Reloading the model for the sake
  of temperature is unnecessary -- it is a request parameter. The price of the
  question is 246 s on Feynman, 19.0% of the chain, i.e. **2.5 cents per book**
  at $0.363/hour. Less than one rejected machine costs ($0.09).
* **"Keep the server alive between passes".** A gain of one and a half cents,
  against the risk of repeating the vLLM orphan disaster.
* **"The witness must re-ask about the same crops".** The markup of the passes
  already matches byte for byte -- there is nothing to fix. (Confirmed again on
  the clean slate: block boxes match byte for byte across all three passes.)

## Transport: small things left alone deliberately

All of low severity, all about `remote/box.py`, which survived. Written down so
as not to be searched for again, and not to be "fixed" when the decision was
not to fix them.

* The fallback `except OSError: _SOCK_DIR = tempfile.gettempdir()` returns the
  socket to the shared `/tmp`, and any local user can trigger it by putting
  `/tmp/.booksmith-<uid>` there as an ordinary file. It does **not get worse**
  than it was, though: before that edit the socket lay in `/tmp` anyway.
* `os.makedirs(mode=0o700)` does not change the mode of an **existing**
  directory, and a symlink to somebody else's directory passes silently. The
  "ran it under sudo once" scenario is closed by the user id in the name; a
  deliberate local adversary remains.
* A `TMPDIR` longer than ~87 characters gives `ControlPath too long` and rc=255
  on every ssh -- fatal, with no fallback to an ordinary connection. The unix
  socket path limit is 108 bytes and the worst real path is **47 bytes**; the
  comment in the code said 42, having left the five-digit port out of the count
  (fixed).
* The fallback `scp` in `push()` is called on any non-zero code, 124 included,
  and goes without a `timeout`. Of no practical weight: `ServerAlive*` kill it
  in ~60 s, and 3.5 MB is what gets uploaded.
