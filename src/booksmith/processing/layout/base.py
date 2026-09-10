"""The Detector contract: what a layout model adapter must return.

In: a page image, its index and dpi. Out: a `Page` of boxes carrying the
model's own labels, coordinates in page pixels at `dpi` -- both stored, or two
runs at different resolutions are incomparable.

Three rules: nobody edits the model's box (no merges, no cuts across the
gutter, no thresholds of ours); what was recognised is untouchable, and
everything observed lives beside the block tied by `block_id`; the label stays
in the model's vocabulary, translated by a map the adapter declares.
"""
import abc

from booksmith.core import policy as policy_mod
from booksmith.core.page import Page


class Detector(abc.ABC):
    """What a model adapter must be able to do -- renting, passes and the
    ledger are the runner's business, assembling the document level two's.
    `tests/contract/test_models_contract.py` checks the list both ways.
    """

    name: str = ""

    # Where the weights came from, for an adapter that holds them; no default,
    # so a silent adapter raises. A served model has none and answers `where`.
    dir: str

    # The model's own vocabulary in its own spelling; no default, as above.
    labels: tuple[str, ...]

    # The weights file, whose size `books doctor` prints; an in-process
    # adapter's, and no default for one.
    onnx: str

    # Which of the tree's own policies describes the vocabulary; empty means
    # it is derived from the labels, and a served model brings its own.
    policy_name: str = ""

    # Keys the pipeline indexes without a default; the soft ones it reads with
    # `.get` are not listed, since that would claim they are load-bearing.
    PAGE_META_REQUIRED = ("rank_ties", "best_rejected_by_class")
    FINGERPRINT_REQUIRED = ("sha256_weights",)

    @abc.abstractmethod
    def label(self) -> str:
        """The model's own short name, and the directory a run of it lives in
        -- never the adapter's, since `doclayout-onnx` serves three models
        whose runs would otherwise share a directory. No default.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fingerprint(self) -> dict:
        """What tells this run from another: weights, prompts, versions.
        Goes into the snapshot whole; empty is legitimate only for a model
        with genuinely nothing to record.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def knobs_read(self) -> tuple[str, ...]:
        """Which registry knobs this adapter reads, declared rather than
        derived: a read can hide outside the class, arrive from a caller's
        default or never pass through `knob()`. No default; () means none.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def read(self, image_path: str, index: int, dpi: float) -> Page:
        raise NotImplementedError

    def where(self) -> str:
        """Where the model is: the weights directory, or the address a served
        model was reached at. For the log and the doctor, never the identity."""
        return self.dir

    def policy(self) -> policy_mod.Policy:
        """The mapping of this model's labels onto the classes: the tree's own
        policy named by `policy_name`, else the one whose labels are exactly
        these. A served model overrides this with what its describe said."""
        got = getattr(self, "_policy", None)
        if got is None:
            got = (policy_mod.POLICIES[self.policy_name] if self.policy_name
                   else policy_mod.for_labels(self.labels))
            self._policy = got
        return got

    def served(self) -> dict | None:
        """The describe a served model answered with, as JSON, or None for a
        model this process holds. `detect.py` writes it into the snapshot and
        folds its knob values into the identity."""
        return None

    def label_map(self) -> dict[str, str]:
        """Model labels into the common vocabulary; empty means they coincide.
        The label metric compares translated names but keeps the originals, so
        a translation error stays separable from a model error.
        """
        return {}

    @abc.abstractmethod
    def threshold_drift(self) -> tuple[str, ...]:
        """Lines about a threshold that is not the weights' own, or ();
        `detect.py` prints each. No default: where ours acts instead of the
        vendor's the adapter must say so rather than stay silent.
        """
        raise NotImplementedError
