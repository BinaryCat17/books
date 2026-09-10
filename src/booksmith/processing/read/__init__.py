"""Level two: the contract for reading a block's content with a vision model.

Declares what "read a block" means -- the values `Route`, `Ask`, `Said` and the
contracts `Reader`, `Transport` -- and no request, path on disk or model name.
What we ask belongs to the model, how we deliver to the transport, and the two
change apart.

The prompt declares the content kind, never the answer; a kind guessed from the
answer lives in `Said.meta` as a counter. Only a delivery failure, where no
answer came at all, is ever repeated: no block is asked twice about its content.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Route:
    """What to ask the model about a block with this label.

    An empty `prompt` means the block is not asked, and then `why` is required:
    "not asked" is a value with a reason. `kind` is the kind this prompt
    promises, one of `core.page.KINDS`, held by `check()` rather than by trust.
    """
    prompt: str
    kind: str = ""
    why: str = ""

    def asked(self) -> bool:
        return bool(self.prompt)

    def check(self, label: str) -> None:
        """Refuse a route that cannot be honoured: a prompt with no kind, an
        unknown kind, or an unasked block with no reason."""
        from booksmith.core.page import KINDS
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
    """One question to the model. Frozen: a transport that edited the prompt
    would get a plausible answer to a question the snapshot does not hold.

    `image` is the path to the crop `core/raster.py` has made; the bytes are the
    transport's business, and the image sha256 rides back beside the answer so
    "the model read the wrong thing" can be told from "we sent the wrong crop".
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

    Three outcomes stay apart: `text` is the model's bytes (`None` no answer
    came, `""` an answer of emptiness), `error` a delivery that never arrived,
    `finish` why generation ended (`None` is "the server did not say").
    """
    anchor: str
    text: str | None = None
    finish: str | None = None
    error: str | None = None
    took_s: float = 0.0
    tokens: int | None = None
    raw: dict | None = None
    # observed beside the answer -- tokens, seconds, the kind guess; never inside `text`
    meta: dict = field(default_factory=dict)

    def answered(self) -> bool:
        """An answer arrived, even an empty one; a delivery failure is not one."""
        return self.error is None and self.text is not None

    def to_json(self) -> dict:
        return {"anchor": self.anchor, "text": self.text,
                "outcome": self.finish, "error": self.error,
                "seconds": round(self.took_s, 3), "tokens": self.tokens,
                "raw_answer": self.raw, "observed": self.meta}


class Reader:
    """What a model adapter must do: name itself so the run repeats, declare its
    knobs, declare what to ask about which label. No address, retries, renting
    or page walk. `routes` is declared, never derived from the label -- each
    detector's vocabulary is its own, and there is no default prompt.
    """

    name: str = ""

    def label(self) -> str:
        """The model's own short name, and the directory a run of it lives in.

        `name` is the reader; this names what answered. Behind an
        OpenAI-compatible endpoint it is what we asked for rather than what
        served, and the transport checks the answering name against it.
        """
        raise NotImplementedError

    def fingerprint(self) -> dict:
        """What tells this run from another. Goes into the snapshot whole.

        Must carry "weights": where the weights are invisible a declared
        emptiness with a reason stands there, never a silent `null`.
        """
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        """Which registry knobs this adapter reads, as a list.

        Only the ones it really reads: a snapshot naming an irrelevant knob is
        complete and inoperative, and `books replay --check` approves it.
        """
        raise NotImplementedError

    def routes(self) -> dict[str, Route]:
        """Detector label -> what to ask. Complete by construction."""
        raise NotImplementedError

    def pixels(self) -> tuple[int, int] | None:
        """(minimum, maximum) crop pixels the model really eats.

        Both bounds are the model's own, not ours: below the lower one it
        stretches the crop, above the upper one it shrinks it. `None` is "the
        model declared no bounds", and then the resolution is the scan's own.
        """
        return None

    def cover(self, labels) -> None:
        """Check that every label of the detector's vocabulary has a route.

        Runs before the first request and the first cent; a label without a
        route is refused, since asking "OCR:" about a table records prose.
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
    """What a delivery method must do: name itself, declare its knobs, say what
    the other side answers with (`check`), deliver one question (`send`). Of
    prompts, labels and OTSL it knows nothing. `check` is separate because it
    runs before the first paid request and prints quantities -- an orphan server
    of a previous run answers a health check as happily as a fresh one.
    """

    name: str = ""

    def fingerprint(self) -> dict:
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        raise NotImplementedError

    def check(self, model: str | None = None) -> dict:
        """What the address answers with, and whether it is what we ask for.
        Quantities, not "ok"."""
        raise NotImplementedError

    def send(self, ask: Ask) -> Said:
        """One question, one answer. A failure returns as a value, not a throw:
        a run over hundreds of blocks must not die of one lost connection."""
        raise NotImplementedError
