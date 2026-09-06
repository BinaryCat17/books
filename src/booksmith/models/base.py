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
from booksmith.core.page import Page


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
