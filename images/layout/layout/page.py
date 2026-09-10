from dataclasses import dataclass, field, asdict


@dataclass
class Block:
    block_id: int
    box: tuple[float, float, float, float]
    label: str
    score: float | None = None
    order: int | None = None
    content: str | None = None
    kind: str = "none"
    source_category: str | None = None

    def area(self) -> float:
        x0, y0, x1, y1 = self.box
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


@dataclass
class Page:
    index: int
    width: int
    height: int
    dpi: float
    blocks: list[Block] = field(default_factory=list)
    raw: dict | None = None
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        for b in d.get("blocks", []):
            if b.get("source_category") is None:
                b.pop("source_category", None)
        return d

    @staticmethod
    def from_json(d: dict) -> "Page":
        blocks = [Block(**{**b, "box": tuple(b["box"])}) for b in d.get("blocks", [])]
        return Page(
            index=d["index"],
            width=d["width"],
            height=d["height"],
            dpi=d["dpi"],
            blocks=blocks,
            raw=d.get("raw"),
            meta=d.get("meta", {}),
        )


KINDS = ("html", "otsl", "latex", "text")
