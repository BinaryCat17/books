"""The on-disk page: what level one returns and level two fills in.

One shape for a detected page, a truth page and a read page: `Page` with
`Block`s. Truth under `bench/*/truth/`, a detect run's `pages/` and a read
run's `pages/` all carry exactly `Page.to_json()`, which is why one metric can
compare any two of them. What may be done to a block is stated in
`layout/base.py`, beside the adapter contract; this file is the shape only.

`KINDS` names what a read block's `content` may be treated as, minus `none`,
which is what an unread block carries.
"""
import json
import os
from dataclasses import dataclass, field, asdict

from booksmith.core.errors import Unmeasurable



@dataclass
class Block:
    """One block as the model saw it: box, label, score, order, content, kind.

    `box` is (x0, y0, x1, y1) in page pixels at `Page.dpi`, origin top left;
    `label`, `score` and `order` are the model's own.
    """
    block_id: int
    box: tuple[float, float, float, float]
    label: str
    score: float | None = None
    # The model's rank, None where the pipeline kept none; holes and ties travel on.
    order: int | None = None
    # What the model returned, byte for byte; parsing it is level two's work.
    content: str | None = None
    kind: str = "none"
    # Truth only: the AnnoPage category a librarian marked, traceable past our label.
    source_category: str | None = None

    def area(self) -> float:
        x0, y0, x1, y1 = self.box
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


@dataclass
class Page:
    """The whole page: the model's blocks and the circumstances of the read."""
    index: int
    width: int
    height: int
    dpi: float
    blocks: list[Block] = field(default_factory=list)
    # The model's answer before parsing: "the model said so" apart from "we parsed it so".
    raw: dict | None = None
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        # Truth-only provenance stays out of output; absent means absent.
        for b in d.get("blocks", []):
            if b.get("source_category") is None:
                b.pop("source_category", None)
        return d

    @staticmethod
    def from_json(d: dict) -> "Page":
        # `box` comes back a tuple, or a block read from disk is unequal to its original.
        blocks = [Block(**{**b, "box": tuple(b["box"])})
                  for b in d.get("blocks", [])]
        return Page(index=d["index"], width=d["width"], height=d["height"],
                    dpi=d["dpi"], blocks=blocks, raw=d.get("raw"),
                    meta=d.get("meta", {}))


# Declared, not "any string": `kind` reaches the journal and the book as an attribute.
KINDS = ("html", "otsl", "latex", "text")


def anchor(index: int, block_id: int | None = None) -> str:
    """The address of a block, `p<index>-b<block_id>` with the index four digits
    wide, or of the page alone when no block is named; block ids restart on
    every page, so the page is part of a block's."""
    p = f"p{index:04d}"
    return p if block_id is None else f"{p}-b{block_id}"


def write_json(path: str, obj: object, indent: int | None = None) -> None:
    """Write `obj` as JSON through a temp file beside `path` and `os.replace`,
    so a reader never sees a truncated file and a death mid-write leaves the
    old one in place."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------- order ---
# The one rule for page `meta["reading_order"]`, for its writers and its readers.
OUR_ORDER = "ours"


def ours_order(value: object) -> bool:
    """Is this our order, by the value of `meta["reading_order"]`.

    Anything that is not a string is unknown, not "the model's": False, and the
    decision is the caller's. The `ours` prefix is the whole signal, case-blind.
    """
    return isinstance(value, str) and value.strip().lower().startswith(OUR_ORDER)


# ----------------------------------------------------------- the loader ---
# Here rather than in `datasets` because `processing` reads pages too and may not import it.
def load_pages(d: str, what: str = "pages") -> dict:
    """Pages of a directory keyed by index: `*.json` except the snapshots.

    Every file must carry `blocks` and `index`, and a directory with none is
    `Unmeasurable`, never an empty result -- empty reads as "matched zero".
    """
    if not os.path.isdir(d):
        raise Unmeasurable(f"{what}: no directory {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name in ("run.json", "manifest.json"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if not (isinstance(p, dict) and "blocks" in p and "index" in p):
            raise Unmeasurable(f"{what}: {name} in {d} does not look like a "
                               f"markup page (no blocks/index)")
        out[int(p["index"])] = p
    if not out:
        raise Unmeasurable(f"{what}: no markup pages in {d}")
    return out
