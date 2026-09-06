"""THE ON-DISK PAGE: what level one returns and level two fills in.

One shape for a detected page, a truth page and a read page: `Page` with
`Block`s. Truth files under `bench/*/truth/`, detection under a run's
`pages/` and reading under its own run's `pages/` all carry exactly
`Page.to_json()`, which is why one metric can compare any two of them.
(Runs live under `<book>/detect/` and `<book>.detect.read/` today; the plan's
step 3b puts them under `detect/<label>/` and `read/<label>/`.) The rules about what may be done to a block are in
`models/base.py`, beside the adapter contract; this file is the shape only.

`KINDS` names what a read block's `content` may be treated as, minus `none`,
which is what an unread block carries. The reading contract checks a route
against it and the swap layer refuses a kind outside it.
"""
import json
import os
from dataclasses import dataclass, field, asdict

from booksmith.core.errors import Unmeasurable



@dataclass
class Block:
    """One block as the model saw it.

    `box` is (x0, y0, x1, y1) in page pixels at `Page.dpi`, origin top left;
    `label`, `score` and `order` are the model's own, `order` being `None` when
    it gives no reading order.

    Measured over the stored runs: `order` is `null` on 2645 blocks of 9546
    (27.7 %), and on all blocks of exactly one page in 539. The zero follows
    the label strictly -- 100 % for `image` (683 of 683), `figure_title` (695),
    `table` (584), `number` (534), `header` (88), 0 % for `text`,
    `paragraph_title`, `display_formula` -- so order was dropped for precisely
    what level one crops out as pictures.

    The raw detector ranks EVERY box (1254 of 1254 on 65 `bench/` pages), so
    `None` here is the pipeline, not the model. Ranks arrive WITH HOLES (where
    the threshold removed a box) and sometimes TIED: 48 boxes on 18 of those 65
    pages share an equal rank, among them `{table, text}` pairs on one
    rectangle. Untying is not ours to do -- the tie travels on.

    `content` is what the model returned, byte for byte; `kind` says what to
    treat it as. Parsing it is level two's work, not the adapter's.
    """
    block_id: int
    box: tuple[float, float, float, float]
    label: str
    score: float | None = None
    order: int | None = None
    content: str | None = None
    kind: str = "none"

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
    # The model's answer before any parsing, kept so that "the model answered
    # so" stays separable from "we parsed it so" when the metric shows
    # something odd.
    raw: dict | None = None
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        # `asdict` unfolds nested dataclasses itself; the former extra line
        # over `blocks` did that work twice.
        return asdict(self)

    @staticmethod
    def from_json(d: dict) -> "Page":
        # `box` must come back a TUPLE: json returns a list, and a block
        # written to disk and read back would be unequal to its original,
        # `(1,2,3,4) != [1,2,3,4]`. For a layer whose declared job is making
        # two runs comparable that is material; `core/knobs.py` says the same
        # about string defaults.
        blocks = [Block(**{**b, "box": tuple(b["box"])})
                  for b in d.get("blocks", [])]
        return Page(index=d["index"], width=d["width"], height=d["height"],
                    dpi=d["dpi"], blocks=blocks, raw=d.get("raw"),
                    meta=d.get("meta", {}))


# Content kinds the second level may return. DECLARED, not "any string": `kind`
# travels into the journal and into the book as an attribute, and a typo would
# silently become a kind nobody agreed on. Names as in the block contract
# (`Block.kind` above), minus its `none` — an unread block has nothing to place.
KINDS = ("html", "otsl", "latex", "text")


# --------------------------------------------------------------- order ---
# The contract for the page `meta` field `reading_order`, kept HERE because
# adapters write that field and it already has two readers:
# `metrics._model_has_rank` (compare order with truth at all?) and
# `doc/html.build` (what to print into the build log). Both once read the
# string's first word by THEIR OWN copy of the rule.
#
# The price of drift was paid by the instrument next door: on `bench/hard36`
# the metric printed "reading order agreed 73 %" where order is annotated on
# none of the 36 pages. A number out of nothing is born exactly so -- two
# copies of one convention written down nowhere.
OUR_ORDER = "ours"


def ours_order(value) -> bool:
    """Is this our order -- by the value of `meta["reading_order"]`.

    Anything that is not a string (`None`, a missing field) is NOT "the
    model's" but unknown: this function cannot answer for it, says False and
    leaves the decision to the caller.

    THE `ours` PREFIX IS THE WHOLE SIGNAL, and case is stripped on purpose:
    the capitalised wording `doclayout.fingerprint` once used would otherwise
    have read, in page meta, as MODEL RANK, and the metric would have scored
    our own numbering against truth. Held by `test_guard_ignores_case`; today
    fingerprint and page meta spell it identically, lower case.
    """
    return isinstance(value, str) and value.strip().lower().startswith(OUR_ORDER)


# ----------------------------------------------------------- the loader ---
# One loader for a directory of pages. It lives here and not in `datasets`
# because the ink measurement in `processing` reads pages too, and processing
# may not import datasets.
def load_pages(d: str, what: str = "pages") -> dict:
    """Pages of a directory keyed by index: `*.json` except the snapshots.

    A directory of foreign json would yield a plausible number about
    nothing, so every file must carry `blocks` and `index`; a directory with
    none is `Unmeasurable`, not an empty result, because an empty result
    reads as "matched zero", which is another thing.
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
