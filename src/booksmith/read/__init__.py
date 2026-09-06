"""Level two: the contract for reading a block's content with a vision model.

Here and only here is it declared WHAT "read a block" means -- three values
(`Route`, `Ask`, `Said`) and two contracts, and not one request, path on disk
or model name.

WHY THE SEAM RUNS HERE. What we ASK belongs to the MODEL, how we DELIVER to the
TRANSPORT, and they change apart: a new model is one `Reader` file with not a
line in the transport, a new delivery one `Transport` file with not a line in
the models. `Ask` and `Said` stand between them, both immutable.

THREE OUTCOMES, NOT TWO: `Said` keeps `text`, `error` and `finish` apart,
because "the model said nothing", "delivery did not arrive" and "cut off at the
answer ceiling" want three different repairs. The third is the expensive one --
the vendor's `otsl_pad_to_sqr_v2` silently truncates rows longer than the
"optimal width", so a table torn at the ceiling comes back PLAUSIBLE and short
rather than broken (`docs/ocr-notes.md`), and `finish` alone tells it apart.

THE PROMPT DECLARES THE CONTENT KIND, NOT THE ANSWER. Asked "Table
Recognition:" means `otsl`, whatever the model replies. Sniffing the kind out
of the answer would repair the model: a table labelled `display_formula` at
0.95 by level one and honestly returned as an array of LaTeX
(`docs/ocr-notes.md`, p. 40) would be recorded as latex, and a LABEL error on a
correct box would dissolve into "that is how the model reads". The guess lives
BESIDE, in `Said.meta`, as a named counter rather than a silent fix.

DELIBERATELY ABSENT: re-asking. Neither side may ask a second question about
the same block after seeing the answer -- "nobody repairs the model" broken in
its purest form, correcting output the measurement never learns about. Only a
delivery failure, where no answer came at all, may be repeated; `http.py` says
so in code.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Route:
    """What to ask the model about a block with this label.

    An empty `prompt` means the block is NOT ASKED, and then `why` is required:
    a VALUE with a reason. PaddleOCR-VL has several, each silent by its own
    measurement -- reading inside figures was tried and rejected (+2100 words
    of rubbish over twenty pages, a schoolbook pangram invented from a line
    drawing), while the answer shape for `chart` and `seal` was never measured
    once, and naming it blind would lie in the field the book decides what to
    show by.

    `kind` is the kind this prompt PROMISES: the names of the block contract
    (`models/base.py`) and of `doc/apply.KINDS`, held by a check, not by trust.
    """
    prompt: str
    kind: str = ""
    why: str = ""

    def asked(self) -> bool:
        return bool(self.prompt)

    def check(self, label: str) -> None:
        """A route must make sense. Silent rubbish here would cost a whole book
        read with the wrong prompt."""
        from ..doc.apply import KINDS
        if self.prompt and not self.kind:
            raise ValueError(
                f"label {label!r}: there is a prompt but no content kind. "
                f"The kind is declared by the PROMPT, not by the answer, and "
                f"the adapter must name it; otherwise the book will not know "
                f"what to show.")
        if self.prompt and self.kind not in KINDS:
            raise ValueError(
                f"label {label!r}: the kind {self.kind!r} is not declared, I "
                f"know only {KINDS}. A typo here would silently start a new "
                f"kind nobody agreed on, and ride into the book as an "
                f"attribute.")
        if not self.prompt and not self.why:
            raise ValueError(
                f"label {label!r}: the block is not asked about, and no "
                f"reason is named. \"Not asked\" is a VALUE, and without a "
                f"reason it cannot be told from a forgotten label.")


@dataclass(frozen=True)
class Ask:
    """One question to the model. Frozen, and not for beauty: a transport
    appending "now do it better" to the prompt would get a plausible answer to
    a DIFFERENT question while the snapshot held the first.

    `image` is the path to the crop `doc/crop.py` has already made; the bytes
    are the transport's business, since deliveries carry them differently. The
    image `sha256` rides back beside the answer -- without it "the model read
    the wrong thing" cannot be told from "we sent the wrong crop", which has
    happened here at level one and cost a rental: a loop variable overwrote the
    scale factor, and 36 pages of 36 were recorded unparsed while the model's
    answer was flawless.
    """
    anchor: str
    image: str
    prompt: str
    kind: str
    label: str
    params: dict = field(default_factory=dict)


@dataclass
class Said:
    """What came of one question. Nobody edits the bytes of `text`.

    The outcome fields are SEPARATE, and that is the main thing in this file:

        text   -- the model's bytes as they arrived. `None` is "no answer
                  came", an empty string "the model answered with emptiness".
        error  -- delivery did not arrive: break, timeout, a code other than
                  200. No answer at all, and NOT the model's silence.
        finish -- why generation ended: `"stop"` | `"length"` | `None`. `None`
                  is "the server did not say", not "it was cut off".

    `meta` is everything observed beside: tokens, seconds, the guess about the
    kind, a model-name mismatch. Nothing enters `text` -- what was recognised
    is untouchable, and that rule already cost nine misses of thirty-three when
    marks were written into the markup.
    """
    anchor: str
    text: str | None = None
    finish: str | None = None
    error: str | None = None
    took_s: float = 0.0
    tokens: int | None = None
    raw: dict | None = None
    meta: dict = field(default_factory=dict)

    def answered(self) -> bool:
        """There IS an answer, even an empty one. A delivery failure is not."""
        return self.error is None and self.text is not None

    def to_json(self) -> dict:
        return {"anchor": self.anchor, "text": self.text,
                "outcome": self.finish, "error": self.error,
                "seconds": round(self.took_s, 3), "tokens": self.tokens,
                "raw_answer": self.raw, "observed": self.meta}


class Reader:
    """What a MODEL adapter must be able to do. Exactly three things.

    Name itself so the run repeats (`fingerprint`), declare its knobs
    (`knobs_read`), declare what to ask about which label (`routes`). No
    address, retries, renting or page walk -- that is the point of the cut.

    WHY `routes` IS DECLARED, NOT DERIVED FROM THE LABEL: the label vocabulary
    is each detector's OWN (25 names in PP-DocLayoutV2, 20 in plus-L, 17 in
    each docling model, 11 in DocLayNet), so "whatever I do not know I ask as
    text" would silently take the twenty-sixth class of new weights to the
    wrong prompt. `cover()` checks completeness and drops the run BEFORE the
    first request.
    """

    name: str = ""

    def fingerprint(self) -> dict:
        """What tells this run from another. Goes into the snapshot whole.

        Must carry the "weights" key. Behind a foreign API the weights are
        invisible, and then a DECLARED emptiness with a reason stands there,
        not a silent `null`: "weights invisible, model behind a foreign API"
        and "weights not looked at" are different runs.
        """
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        """Which registry knobs THIS adapter reads. As a list.

        The detectors' disease, and it has already happened: a heron run's
        snapshot confidently wrote `LAYOUT_MODEL_NAME=PP-DocLayoutV2` -- a
        value irrelevant to that run -- and `books replay --check` approved it.
        The snapshot was COMPLETE and inoperative, which is worse than a gap.
        """
        raise NotImplementedError

    def routes(self) -> dict[str, Route]:
        """DETECTOR LABEL -> what to ask. Complete by construction."""
        raise NotImplementedError

    def pixels(self) -> tuple[int, int] | None:
        """(minimum, maximum) crop pixels the model REALLY eats.

        DECLARED BY THE MODEL, NOT BY US. "Which dpi to set" long stood as a
        choice of number, and any number here would have been ours. Both bounds
        are foreign: below the lower one the model stretches the crop, above
        the upper one it shrinks it. So cut as much as the scan HAS, and no
        more than the model eats.

        Measured: `bench/slovar` crops at detection resolution have a median of
        12 195 pixels, and 555 of 566 sit below PaddleOCR-VL's lower bound of
        112 896. Our own books come from djvu with a 601 dpi text layer, where
        the same block is about 212 thousand -- inside the window -- while a
        table would spread to three million, three times over the upper bound,
        paying for bytes the model throws away at once.

        `None` is "the model declared no bounds", a VALUE: the resolution is
        then the scan's own, corrected by nothing, and the ledger says so.
        """
        return None

    def cover(self, labels) -> None:
        """Check that EVERY label of the detector's vocabulary has a route.

        Called before the first request and the first cent. A label without a
        route is refused aloud: a silent default of "ask OCR:" would read a
        table as prose and record that as the reading.
        """
        r = self.routes()
        for lab in sorted(labels):
            if lab not in r:
                raise ValueError(
                    f"the reader {self.name!r} does not know what to ask "
                    f"about the label {lab!r}. There is no default here on "
                    f"purpose: asking \"OCR:\" about a table means getting "
                    f"prose and recording it as the reading. Declare a route "
                    f"-- an empty one with a reason will do.")
            r[lab].check(lab)


class Transport:
    """What a DELIVERY method must be able to do. Four things.

    Name itself, declare its knobs, say what the other side answers with
    (`check`) and deliver one question (`send`). Of prompts, labels and OTSL it
    knows nothing.

    `check` IS A SEPARATE METHOD, not a line inside `send`: it must run BEFORE
    the first paid request and print quantities. The trouble it exists for was
    paid at level one -- the `curl /v1/models` health check was answered by an
    ORPHAN of the previous run holding 60 % of the video memory, and the script
    believed it had raised the server itself.
    """

    name: str = ""

    def fingerprint(self) -> dict:
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        raise NotImplementedError

    def check(self, model: str | None = None) -> dict:
        """What the address answers with and whether it is what we ask for.
        Quantities, not "ok"."""
        raise NotImplementedError

    def send(self, ask: Ask) -> Said:
        """One question, one answer. A failure returns as a VALUE, not a throw:
        a run over five hundred blocks must not die of one lost connection."""
        raise NotImplementedError
