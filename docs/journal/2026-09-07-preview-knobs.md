# 2026-09-07: the VLM-input preview and its three knobs, as they stood when they went

`doc/feed.py` and the knobs `VLM_INPUT`, `MASK_FILL` and `FEED_DPI` were
deleted in step 3a's second half: no reader on the paid path (`knobs.
readers()` named `doc/feed.py` alone for all three), and the preview cut
with its own dpi and its own hole-fill, so it showed pictures `books read`
never sent. `books crop` replaced it: the read driver in preview, cutting
by its own rule and sending nothing.

What the module recorded is kept here verbatim, because it was measured
and paid for, and the correction stage of the plan (step 4) will meet the
same questions.

## The header of `doc/feed.py`

> What exactly goes to the VLM: a crop by box, or a page with holes.
>
> Two feeds, HYPOTHESES both when written. `crop` has since run for real --
> `books read`, 436 pages, $0.545; `masked_page` never has, and cannot from
> the paying path: `books read` cuts its own crops and never asks
> `VLM_INPUT`, which only `books feed` reads. The two are still unmeasured
> against each other.
>
>     crop         one request per text block, as the PaddleOCR-VL pipeline
>                  ships: measured on an earlier run, 409 requests over 25
>                  pages, sixteen a page.
>     masked_page  one request per page, artifacts painted over. Sixteen
>                  times fewer calls, and the model sees coherent text
>                  whole -- hyphenation, columns, a paragraph continuing
>                  past a figure.
>
> In BOTH, artifacts do not go to the VLM at all. That is the first level:
> read the text, cut tables and figures out as pictures, do not parse them.
> Looking inside a figure was tried and rejected -- the pangram `The quick
> brown fox` invented off a line drawing, +2100 words of rubbish over 20
> pages.
>
> WHAT IS KNOWN AGAINST `masked_page`, BEFORE THE MEASUREMENT.
>
> * **Empty space does not keep quiet.** The probe "a blank white sheet":
>   five tries, five different Chinese office tables. A painted rectangle
>   is that sheet in miniature, and an invented table can appear in its
>   place. So what to paint with is the `MASK_FILL` knob, not a constant:
>   white is the least neutral choice there is.
> * **Context spoils reading.** Remove the third column and the model read
>   the second right; with the whole page it read it wrong. Here isolation
>   helped.
> * **The answer ceiling.** The pipeline lowers `max_new_tokens` to 4096,
>   while the longest SINGLE text block in our books is 8207 characters. A
>   whole page is bigger, and a cutoff in this model looks like looping.

## The knobs' own words

* `VLM_INPUT` (default `crop`): "what to feed the VLM: crop | masked_page".
  Above it in the registry: none of the three measurements was taken on a
  whole masked page -- hence a knob and not a decision.
* `MASK_FILL` (default `white`): "hole fill under masked_page:
  white|gray|black". Not a constant: white is the least neutral option
  there is, and it was on blank white that the model invented tables.
* `FEED_DPI` (default empty): "resolution of the page going to the VLM;
  empty = as PAGE_DPI". Its reason for existing: so that `CROP_DPI` would
  not silently set the whole-page feed's resolution too (a fourfold token
  count at 300 dpi against 144).

## What survives in code

The blank-sheet fact stands where it is enforced: the transport refuses an
empty crop (`transports/openai_http.py`), because an empty picture is the
sheet on which the model invented five tables. The union-of-holes
geometry the preview wrote is the builder's now (`assemble/html.py`), its
last reader.
