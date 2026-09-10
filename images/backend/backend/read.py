from dataclasses import dataclass, field


@dataclass(frozen=True)
class Route:
    prompt: str
    kind: str = ""
    why: str = ""

    def asked(self) -> bool:
        return bool(self.prompt)

    def check(self, label: str) -> None:
        from backend.page import KINDS

        if self.prompt and (not self.kind):
            raise ValueError(
                f"label {label!r}: there is a prompt but no content kind. The kind is declared by the PROMPT, not by the answer, and the adapter must name it; otherwise the book will not know what to show."
            )
        if self.prompt and self.kind not in KINDS:
            raise ValueError(
                f"label {label!r}: the kind {self.kind!r} is not declared, I know only {KINDS}. A typo here would silently start a new kind nobody agreed on, and ride into the book as an attribute."
            )
        if not self.prompt and (not self.why):
            raise ValueError(
                f'label {label!r}: the block is not asked about, and no reason is named. "Not asked" is a VALUE, and without a reason it cannot be told from a forgotten label.'
            )


@dataclass(frozen=True)
class Ask:
    anchor: str
    image: str
    prompt: str
    kind: str
    label: str
    params: dict = field(default_factory=dict)


@dataclass
class Said:
    anchor: str
    text: str | None = None
    finish: str | None = None
    error: str | None = None
    took_s: float = 0.0
    tokens: int | None = None
    raw: dict | None = None
    meta: dict = field(default_factory=dict)

    def answered(self) -> bool:
        return self.error is None and self.text is not None

    def to_json(self) -> dict:
        return {
            "anchor": self.anchor,
            "text": self.text,
            "outcome": self.finish,
            "error": self.error,
            "seconds": round(self.took_s, 3),
            "tokens": self.tokens,
            "raw_answer": self.raw,
            "observed": self.meta,
        }


class Reader:
    name: str = ""

    def label(self) -> str:
        raise NotImplementedError

    def fingerprint(self) -> dict:
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        raise NotImplementedError

    def routes(self) -> dict[str, Route]:
        raise NotImplementedError

    def pixels(self) -> tuple[int, int] | None:
        return None

    def cover(self, labels) -> None:
        r = self.routes()
        for lab in sorted(labels):
            if lab not in r:
                raise ValueError(
                    f'the reader {self.name!r} does not know what to ask about the label {lab!r}. There is no default here on purpose: asking "OCR:" about a table means getting prose and recording it as the reading. Declare a route -- an empty one with a reason will do.'
                )
            r[lab].check(lab)


class Transport:
    name: str = ""

    def fingerprint(self) -> dict:
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        raise NotImplementedError

    def check(self, model: str | None = None) -> dict:
        raise NotImplementedError

    def send(self, ask: Ask) -> Said:
        raise NotImplementedError
