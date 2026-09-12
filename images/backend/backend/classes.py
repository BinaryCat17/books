from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from backend import settings
from backend.errors import Unmeasurable


with open(os.path.join(settings.schema_dir(), "classes.json"), encoding="utf-8") as _f:
    _TABLE = json.load(_f)
TABLE = {k: v for k, v in _TABLE.items() if not k.startswith("$")}

ROLES = ("text", "artifact", "furniture")
ORDER_NAMES = (
    "caption",
    "code",
    "footnote",
    "page_footer",
    "page_header",
    "picture",
    "table",
    "text",
)
CLASSES: dict[str, tuple[str, str]] = {n: (c["role"], c["order"]) for n, c in _TABLE["classes"].items()}


class UnknownLabel(Unmeasurable):
    pass


@dataclass(frozen=True)
class Policy:
    name: str
    classes: Mapping[str, str]

    def __post_init__(self) -> None:
        bad = {lab: c for lab, c in self.classes.items() if c not in CLASSES}
        if bad:
            raise UnknownLabel(
                f"policy {self.name or 'of the model'}: labels mapped onto classes the tree does not declare: {bad}. The classes are {sorted(CLASSES)}; there is no default on purpose."
            )
        if not all(isinstance(lab, str) and lab for lab in self.classes):
            raise UnknownLabel(f"policy {self.name!r}: a label is not a non-empty string")

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(sorted(self.classes))

    def cls(self, label: str) -> str:
        try:
            return self.classes[label]
        except KeyError:
            raise UnknownLabel(
                f"the label {label!r} is not described by the policy {self.name or 'the model declared'} ({len(self.classes)} labels)"
            ) from None

    def role(self, label: str) -> str:
        return CLASSES[self.cls(label)][0]

    def order_name(self, label: str) -> str:
        return CLASSES[self.cls(label)][1]

    def artefacts(self) -> tuple[str, ...]:
        return self.by_role("artifact")

    def by_role(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(lab for lab in self.classes if CLASSES[self.classes[lab]][0] == role))

    def check(self, labels: Iterable[str]) -> None:
        have, mine = (set(labels), set(self.classes))
        who = self.name or "the model's own declaration"
        if have - mine:
            raise UnknownLabel(
                f"the policy {who} does not describe the model's labels: {sorted(have - mine)}. Describe them in the mapping -- there is no default here on purpose."
            )
        if mine - have:
            raise UnknownLabel(
                f"the policy {who} describes labels the model does not have: {sorted(mine - have)}. A typo here shows in nothing but an eternal zero in the report."
            )

    def snapshot(self) -> dict:
        return {
            "buckets": list(ROLES),
            "vocabulary": self.name,
            "by_label": {lab: self.role(lab) for lab in self.labels},
            "classes": {lab: self.classes[lab] for lab in self.labels},
        }

    @staticmethod
    def from_classes(mapping: Mapping[str, str], name: str = "") -> Policy:
        return Policy(name, dict(mapping))

    @staticmethod
    def from_snapshot(d: object) -> Policy:
        if not isinstance(d, dict):
            raise UnknownLabel("the snapshot carries no policy at all")
        classes = d.get("classes")
        if isinstance(classes, dict) and classes:
            return Policy.from_classes(classes, str(d.get("vocabulary") or ""))
        name = d.get("vocabulary")
        if isinstance(name, str) and name in POLICIES:
            return POLICIES[name]
        raise UnknownLabel(
            f"the snapshot names the vocabulary {name!r}, which this tree does not hold, and carries no classes of its own"
        )


VOCABULARIES: dict[str, dict[str, str]] = {n: dict(m) for n, m in _TABLE["vocabularies"].items()}
POLICIES: dict[str, Policy] = {n: Policy(n, m) for n, m in VOCABULARIES.items()}


def _union() -> Policy:
    merged: dict[str, str] = {}
    for name, table in VOCABULARIES.items():
        for lab, c in table.items():
            if merged.get(lab, c) != c:
                raise RuntimeError(
                    f"the label {lab!r} means different things in different vocabularies: {merged[lab]!r} and {c!r} in {name}. The union would silently pick one of the two, and a truth block's class would depend on the import order."
                )
            merged[lab] = c
    return Policy("union", merged)


UNION = _union()


def for_labels(labels: Iterable[str]) -> Policy:
    have = set(labels)
    fit = [p for p in POLICIES.values() if set(p.classes) == have]
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise UnknownLabel(
            f"no policy for a vocabulary of {len(have)} labels: {sorted(have)[:6]}... Describe it in policy.VOCABULARIES, or serve the model with its mapping -- there is no default here on purpose."
        )
    raise UnknownLabel(f"several policies fit this vocabulary: {[p.name for p in fit]}")


def fits(labels: Iterable[str]) -> list[str]:
    have = set(labels)
    return sorted(p.name for p in POLICIES.values() if have <= set(p.classes))
