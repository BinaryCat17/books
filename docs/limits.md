# What this project cannot measure, and the rules that outlive their code

Three kinds of text about this project exist, and mixing them is what made
the same number live in six files at once:

* **The verdict on a model** -- what it is, what it costs, what it found.
  That is `docs/models.md`, one section per model, one place.
* **The laboratory journal** -- how a number was obtained, which traps ate the
  money, what was rejected and why. That is `docs/contour-notes.md` (contours),
  `docs/ocr-notes.md` (reading) and `docs/vast-notes.md` (renting).
* **The price of an error, next to the code that can repeat it.** That stays in
  the module. A warning about `_sheet_trouble` belongs in `doc/html.py`,
  because that is where the next person will break it.

**This file is the fourth kind: what is not knowable yet, and the rules that
survive the code they were learned from.** Nothing here is a plan. Everything
here has already cost something.

---

## 1. The second level cannot be measured, and this must be known before paying

`books read` is the only command that spends money. The temptation is to run
it, look at the CER, and decide something. The number that comes back is a
**lower bound and a proof that the pipe works** -- not a prediction of quality.
Three reasons, each measured:

**The golden bench annotates no text at all.** `bench/annopage/manifest.json`
carries `text_marked: false`, and AnnoPage marks only non-text objects across
25 categories. Six hundred real pages therefore say nothing whatever about
reading. Reading can only be measured on drawn synthetic pages.

**Every bench is drawn at 144 dpi; the real books are 353 to 600.** Measured:
`synth.DPI = 144.0`, and the median raster dpi inside `raw/*.pdf` is 353, 400,
533, 599, 600, 600 (median over the images of the first six pages of each).
A character on the bench is two and a half to four times smaller than the one
the model will meet on a real book.

**The synthetic pages are typeset with a font, not printed by letterpress.**
Stated in the generator's own header since the first day. Ink spread, bitten
serifs and the grey of old paper are imitated by `synth.AGING`, not observed.

**What follows practically.** The number the first paid run returns cannot be
used to choose the input form, the crop sharpness or the model. To make that
possible one needs a bench of real scans with known text, and there is none:
`bench/real` has never been annotated by hand.

---

## 2. What the three instruments do and do not see

There are three, and all three must be read. It used to be said there were
four; the fourth was a line of output from `books score`, counted twice.

| instrument | answers | blind to |
|---|---|---|
| `books score` | did the boxes merge; will the page be read in order | whether the content survives the crop |
| `books fitness` | will the meaning arrive, by ink, with no truth needed | merging -- it cannot punish it by construction |
| `books text` | were the characters and table cells read correctly | anything the detector never boxed |

**Ink alone is not enough to choose a model, and that correction was paid for
later than the rule it corrects.** The docling pipeline costs seven objects
measured by ink and a hundred and thirty-two measured by something that sees
merging. A factor of nineteen.

**A strict metric answers a different question than this pipeline asks.**
Two-sided coverage of 0.75 punishes a merge -- but a merge costs this pipeline
almost nothing, because a wider picture goes to the second level and is split
there. On the 36 hardest pages the difference is fourfold: 20 % by strict
match against 91 % of objects arriving whole.

---

## 3. Data that cannot be regenerated

| what | files | why |
|---|---|---|
| `bench/*/dots*` | 1274 | Counted on a rented RTX 4090. One successful rental of sixteen, $0.892; all sixteen $1.370. No home re-parser exists. |
| `processed/vl-reads/` | 891 | The paid reading: 436 pages and 436 answer files holding 6906 model answers, $0.545 over eight rentals, two of them successful. 915 078 characters. |
| `bench/annopage-lite`, `bench/hard36` | 638 | Built by a script that is in neither the tree nor the git history. `books subset` writes `bench/hard`, not `hard36`. |

Everything else regenerates for free: `books synth --book <name>` (six books),
`books annopage raw/annopage` (600 pages), `books subset` (130).

**The rename of the format keys was done against this list.** A backup of all
6037 json files was taken first, restoring it was proved (6037 of 6037
byte-identical), and `tools/migrate_keys.py` refuses any file whose exact bytes
it cannot first reproduce.

---

## 4. Rules that outlive the code they were learned from

**A metric must be able to fail.** Before believing a number, feed it a
deliberately broken input and watch the number fall. Every battery in this
project exists because of this: `books score --selfcheck`, `books fitness
--selfcheck`, `books text --selfcheck`, `books replay --check --selfcheck`,
and `tests/run.py --selfcheck` over the checks themselves.

**Zero from a check and zero from not understanding are different zeros.**
"Chapters: 0" meant "I did not recognise them" and was read as "the book has
none" -- in all four books at once. Every counter in this project that can mean
both must say which.

**Log the quantity, not the word "done".** Three unfinished jobs surfaced in
one evening only by comparing a number with what was expected: "8 links" for
22 tables, "103 spreads" instead of four.

**Words and structure may be repaired; numbers may only be flagged, never
restored.** Measured across six books: a damaged cell was marked LESS often
than an average one (lift 0.29-0.65 against a line shift), and the leading
form of invisible damage -- a shifted row -- is identical in every pass and
invisible by construction.

**A knob is declared in `run/knobs.py`.** Reading the environment past the
registry is a defect: a knob that is not in the registry does not reach the
snapshot, and the run becomes silently unrepeatable.

**Nobody repairs the model.** No merging of boxes, no cutting across the
gutter, no re-asking, no thresholds tuned by us. What the model returned is
what gets measured. A patch does not improve the book -- it hides the defect
from the measurement.

**What was recognised is untouchable.** Marks, links back to the scan, hyphen
joining -- all of it is a rule about the model's output in place, and it has
already cost: a `⚠` marker was appended before a table's caption was counted,
and nine of thirty-three were missed. Everything observed lives beside the
block and is tied to it by number.

---

## 5. Rules learned while translating this project to English

The translation renamed 908 727 keys in the data and 2769 names in the code.
Fourteen defects surfaced, and all fourteen were of one shape and all fourteen
were silent.

**A name renamed at the writer and not at the reader does not fail -- it
prints a zero.** Three sheet counters in `books html` reported 0 while the book
itself marked two sheets; `books text --norm none` quietly became a synonym for
`boundary`; four mutations in the battery certified nothing because a shadowed
name made them throw instead of measure; `DoclingEgret.fingerprint()` reported
itself as heron.

**A guard must take the name from one side and the number from the other.**
A check that reads both from the code travels with the code: renaming a key in
20 source files left the runner at 243/242/0 and the battery at 218/218, both
byte-identical to the baseline. `booksmith.schema` declares the names and
`bench/` supplies the counts, which is why it fails in both directions.

**Headline numbers are blind to renames.** 698/1232 found, 646 whole, 375
merged, 501 extra jumps -- not one of them moved when all 13 996 Cyrillic keys
in `bench/annopage` were renamed, nor when the rename was stopped halfway. What
moved was the prose around them: a line reading "350 objects out of scope"
simply stopped being printed. Reports are therefore compared whole
(`bench/expected/`), and separately by their numbers as multisets.

**Measuring what is left is not measuring what was done.** Deleting every
comment line carrying Cyrillic removes 176 515 characters -- a quarter of
everything this project has written into its comments -- and leaves every
instrument green while reporting a quarter of the job done. Each area
therefore carries a second number, the Latin in the same prose: translation
turns Cyrillic into Latin, deletion turns it into nothing.
