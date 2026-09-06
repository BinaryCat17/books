"""What the model must return -- and what must never be done to its answer.

The old pipeline had no such layer: model, patching and book build shared one
file of 1948 lines where a dozen `patched` functions edited boxes inside a
foreign pipeline. "What does the model give by itself" was unanswerable -- by
the time anything could be measured the output was already corrected by us.

Hence three rules, none of them stylistic.

**1. Nobody edits the model's box.** No merges, no cuts across the gutter, no
re-asking, no thresholds of ours. A box across the gutter is the model's
defect: it reaches the metric and shows. Patched, it left the measurement, not
the book.

**2. What was recognised is untouchable.** `⚠`, `≠`, `<mark>` and comments
citing the scan used to be appended to the text. Cost: `⚠` entered cells before
the table caption was counted, the box stopped recognising its own table -- 9
misses of 33. Everything observed (probabilities, pass disagreements, crops)
lives beside the block, tied by `block_id`.

**3. The label stays in the model's vocabulary, not ours.** Mapping one
model's `header` onto another's `title` loses the class of error: on p. 40 of
the old bench a table got `display_formula` at 0.95 -- a LABEL error on a
correct box, separate from localisation. The map is declared by the adapter and
snapshotted, so the translation stays reversible.

Coordinates are page pixels at `dpi`; both are stored, or two runs at different
resolutions are incomparable.
"""
from dataclasses import dataclass, field, asdict


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
        # two runs comparable that is material; `run/knobs.py` says the same
        # about string defaults.
        blocks = [Block(**{**b, "box": tuple(b["box"])})
                  for b in d.get("blocks", [])]
        return Page(index=d["index"], width=d["width"], height=d["height"],
                    dpi=d["dpi"], blocks=blocks, raw=d.get("raw"),
                    meta=d.get("meta", {}))


class Recognizer:
    """What a model adapter must be able to do.

    THE LIST USED TO BE SHORTER THAN THE TRUTH, and that is the defect this
    docstring records. It said "exactly two things" and declared five members
    while `detect.py` asked for eight: `dir`, `labels`, `policy_name` and
    `threshold_drift` were used by the pipeline and appeared nowhere in the
    contract. An adapter written to the contract as documented would have got
    through import and fallen at the first run -- and the four missing names
    are exactly the ones with no default anywhere to catch them.

    The contract is now checked against the pipeline rather than believed:
    `tests/test_models_contract.py` reads every attribute `detect.py` asks of
    an adapter and requires it here, and requires every name here to be asked
    for somewhere. It fails in both directions, which a list nobody compares
    cannot do.

    Renting, passes and the ledger are the runner's business; assembling the
    document is level two's.
    """

    name: str = ""

    # WHERE THE WEIGHTS CAME FROM, printed into the detection log and the
    # snapshot. ANNOTATED, NOT DEFAULTED -- the first edition wrote `dir = ""`,
    # which turned "this adapter forgot its weights directory" into a silent
    # `weights 0 MB` in the log. That is the argument this file makes for
    # `knobs_read` and `threshold_drift` having no default, applied here too:
    # an adapter silent out of forgetfulness must be indistinguishable from
    # nothing, which is what an AttributeError is.
    dir: str

    # THE MODEL'S OWN VOCABULARY, in the model's own spelling. `detect.py`
    # counts it and hands it to `policy.check`; annotated for the same reason.
    labels: tuple[str, ...]

    # THE WEIGHTS FILE, whose size `books doctor` prints. Asked for softly --
    # `getattr(det, "onnx", "")` in `cli.py` -- and therefore invisible to a
    # check that only looked at `detect.py` and only at attribute nodes. All
    # three adapters set it; the contract had never said so, and the cost of
    # forgetting is a confident `weights 0 MB`.
    onnx: str

    # Which policy describes that vocabulary. Empty means "work it out from
    # the labels" -- `detect.py` does exactly that and writes the answer back,
    # so this is the one member of the contract the pipeline may fill in.
    policy_name: str = ""

    # WHAT `read` MUST PUT IN A PAGE'S `meta`, AND WHAT `fingerprint` MUST
    # RETURN. Declaring the METHODS was not enough, and a skeptic proved it by
    # writing an adapter to the contract as documented: it imported cleanly,
    # ran, and fell three times in a row on `page.meta["rank_ties"]`,
    # `page.meta["best_rejected_by_class"]` and `fingerprint()["sha256_
    # weights"]` -- subscripts, which no list of attribute names can see.
    #
    # These are REQUIRED, meaning the pipeline indexes them without a default
    # and falls where they are missing. The soft ones -- `model`, `input`,
    # `native_threshold`, `boxes_accepted` -- are read with `.get` and degrade
    # to a poorer log; they are not listed, because listing them would say
    # they are load-bearing when they are not.
    PAGE_META_REQUIRED = ("rank_ties", "best_rejected_by_class")
    FINGERPRINT_REQUIRED = ("sha256_weights",)

    def fingerprint(self) -> dict:
        """What tells this run from another: weights, prompts, versions.

        Goes into the snapshot whole. An empty fingerprint is legitimate only
        for a model with genuinely nothing to record; ours all have something.
        """
        raise NotImplementedError

    def knobs_read(self) -> tuple[str, ...]:
        """Which registry knobs THIS adapter reads. Declared as a list.

        Measured before the field existed: `LAYOUT_ADAPTER=docling` on 12 pages
        of `bench/matematika` wrote `LAYOUT_MODEL_NAME=PP-DocLayoutV2` into the
        snapshot while computing heron, whose weights directory is hardwired in
        `__init__` and whose only `LAYOUT_MODEL_DIR` read lives in a foreign
        file, `doclayout.py`. Same for `LAYOUT_TABLE_THRESHOLD`: neither heron
        nor yolox reads it. The snapshot was formally COMPLETE and `books
        replay --check` returned 0 -- more dangerous than a gap, since the
        value is named confidently and belongs to another run. The `VL_MODEL_DIR`
        disease from the head of `run/knobs.py`, quieter: there the knob went
        past the registry, here past the consumer.

        WHY DECLARED, NOT DERIVED. The one catcher that derived the list by
        parsing sources, `tests/test_knobs_registry.py`, is deleted and not
        restored -- but the read also hides outside the class (`weights_dir()`
        in `doclayout.py`, called from `__init__`), arrives from the caller's
        default (`YoloXLayout(weights=…)` reads no knob at all) or never passes
        through `knob()` -- an `export` in the shell is invisible to any parser
        by construction. A derived list misses such paths silently; a declared
        one is grepped against one file in half a minute, and its drift from
        the code is visible to a human.

        An empty tuple is legitimate ONLY for an adapter with nothing to
        declare (weights hardwired, native threshold). No default on purpose:
        an adapter silent out of forgetfulness would return the snapshot to the
        very disease this field was made for -- confident and wrong.
        """
        raise NotImplementedError

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        raise NotImplementedError

    def label_map(self) -> dict[str, str]:
        """Model labels into the common vocabulary -- declared, not hardwired.

        An empty dict means "the model's vocabulary is the common one". The
        label metric compares translated names but keeps the originals, so a
        translation error stays separable from a model error.
        """
        return {}

    def threshold_drift(self) -> tuple[str, ...]:
        """Lines about a threshold that is NOT the weights' own, or ().

        NO DEFAULT ON PURPOSE, like `knobs_read` beside it. An adapter silent
        out of forgetfulness would be indistinguishable from one whose
        threshold is genuinely the vendor's, and the difference is the whole
        point: YOLOX has no native selection threshold at all, so ours acts,
        and the adapter says so out loud rather than letting a reader assume a
        vendor default. `detect.py` prints every line this returns.
        """
        raise NotImplementedError


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
