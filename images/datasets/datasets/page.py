import json
import os
from dataclasses import dataclass, field, asdict
from datasets.errors import Unmeasurable


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


def load_pages(d: str, what: str = "pages") -> dict:
    if not os.path.isdir(d):
        raise Unmeasurable(f"{what}: no directory {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name in ("run.json", "manifest.json"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if not (isinstance(p, dict) and "blocks" in p and ("index" in p)):
            raise Unmeasurable(f"{what}: {name} in {d} does not look like a markup page (no blocks/index)")
        out[int(p["index"])] = p
    if not out:
        raise Unmeasurable(f"{what}: no markup pages in {d}")
    return out
