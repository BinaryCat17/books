"""The Detector contract: what a layout model adapter must return"""

import abc
from layout import classes as policy_mod
from layout.page import Page


class Detector(abc.ABC):
    name: str = ""
    dir: str
    labels: tuple[str, ...]
    onnx: str
    policy_name: str = ""
    PAGE_META_REQUIRED = ("rank_ties", "best_rejected_by_class")
    FINGERPRINT_REQUIRED = ("sha256_weights",)

    @abc.abstractmethod
    def label(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def fingerprint(self) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def knobs_read(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def read(self, image_path: str, index: int, dpi: float) -> Page:
        raise NotImplementedError

    def where(self) -> str:
        return self.dir

    def policy(self) -> policy_mod.Policy:
        got = getattr(self, "_policy", None)
        if got is None:
            got = (
                policy_mod.POLICIES[self.policy_name]
                if self.policy_name
                else policy_mod.for_labels(self.labels)
            )
            self._policy = got
        return got

    def served(self) -> dict | None:
        return None

    def label_map(self) -> dict[str, str]:
        return {}

    @abc.abstractmethod
    def threshold_drift(self) -> tuple[str, ...]:
        raise NotImplementedError
