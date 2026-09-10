"""What level one does with a block: `text`, `artifact` or `furniture`, by class.

Ours, not the model's: a model names its labels in its own spelling, and
maps each onto one of the classes declared here, whole. A class carries the
role -- `artifact` is cut out as a picture for level two to take apart,
`text` stays text in the flow, `furniture` is running heads, folios and
footnotes, marked and kept -- and the name the vendor's order rules look at.
A reader routes its prompts by class too, in its own module. One table, so a
model the tree has never seen runs by declaring a mapping, and a label absent
from the mapping fells the run: there is no default, and a new class of
weights cannot pour into the prose unnoticed.

A `Policy` is one such mapping with a name. The five the tree's own
adapters use are data below; `UNION` is their union, checked at import for
a label meaning two things, and it stands for truth, which is annotated in
those vocabularies and carries no declaration of its own yet.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from booksmith.core.errors import Unmeasurable

ROLES = ("text", "artifact", "furniture")

# The names the docling order rules read; anything else rides as `text`.
ORDER_NAMES = ("caption", "code", "footnote", "page_footer", "page_header",
               "picture", "table", "text")

# class -> (role, order name). Fifteen, and not fourteen: a program listing is
# `algorithm`, text, in the paddle family and `code`, an artifact, in docling's,
# and one class cannot carry both roles.
CLASSES: dict[str, tuple[str, str]] = {
    "text": ("text", "text"),
    "caption": ("text", "caption"),
    "algorithm": ("text", "code"),
    # Text, not a picture: cutting an inline formula out would tear the sentence.
    "inline_formula": ("text", "text"),
    "code": ("artifact", "code"),
    # A formula as a block is a picture; whether it becomes HTML is level two's.
    "display_formula": ("artifact", "picture"),
    "table": ("artifact", "table"),
    "chart": ("artifact", "picture"),
    "seal": ("artifact", "picture"),
    "picture": ("artifact", "picture"),
    "header_image": ("artifact", "page_header"),
    "footer_image": ("artifact", "page_footer"),
    "page_header": ("furniture", "page_header"),
    "page_footer": ("furniture", "page_footer"),
    "footnote": ("furniture", "footnote"),
}


class UnknownLabel(Unmeasurable):
    """The model's label is not described by the policy. Fell, do not guess."""


@dataclass(frozen=True)
class Policy:
    """One vocabulary: label to class, and a name for the snapshot and the
    log. The name is empty for a served model's own declaration."""
    name: str
    classes: Mapping[str, str]

    def __post_init__(self) -> None:
        bad = {lab: c for lab, c in self.classes.items() if c not in CLASSES}
        if bad:
            raise UnknownLabel(
                f"policy {self.name or 'of the model'}: labels mapped onto "
                f"classes the tree does not declare: {bad}. The classes are "
                f"{sorted(CLASSES)}; there is no default on purpose.")
        if not all(isinstance(lab, str) and lab for lab in self.classes):
            raise UnknownLabel(f"policy {self.name!r}: a label is not a "
                               f"non-empty string")

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(sorted(self.classes))

    def cls(self, label: str) -> str:
        try:
            return self.classes[label]
        except KeyError:
            raise UnknownLabel(
                f"the label {label!r} is not described by the policy "
                f"{self.name or 'the model declared'} ({len(self.classes)} "
                f"labels)") from None

    def role(self, label: str) -> str:
        return CLASSES[self.cls(label)][0]

    def order_name(self, label: str) -> str:
        return CLASSES[self.cls(label)][1]

    def artefacts(self) -> tuple[str, ...]:
        return self.by_role("artifact")

    def by_role(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(lab for lab in self.classes
                            if CLASSES[self.classes[lab]][0] == role))

    def covers(self, labels: Iterable[str]) -> bool:
        return set(labels) <= set(self.classes)

    def check(self, labels: Iterable[str]) -> None:
        """The policy must cover the model's vocabulary whole, and hold nothing
        extra. Checked every run, the vocabulary arriving with the weights."""
        have, mine = set(labels), set(self.classes)
        who = self.name or "the model's own declaration"
        if have - mine:
            raise UnknownLabel(
                f"the policy {who} does not describe the model's labels: "
                f"{sorted(have - mine)}. Describe them in the mapping -- "
                f"there is no default here on purpose.")
        if mine - have:
            raise UnknownLabel(
                f"the policy {who} describes labels the model does not have: "
                f"{sorted(mine - have)}. A typo here shows in nothing but an "
                f"eternal zero in the report.")

    def snapshot(self) -> dict:
        """The policy whole, into the snapshot: the classes, and the roles
        beside them for a reader that knows the three buckets only."""
        return {"buckets": list(ROLES), "vocabulary": self.name,
                "by_label": {lab: self.role(lab) for lab in self.labels},
                "classes": {lab: self.classes[lab] for lab in self.labels}}

    @staticmethod
    def from_classes(mapping: Mapping[str, str], name: str = "") -> Policy:
        return Policy(name, dict(mapping))

    @staticmethod
    def from_snapshot(d: object) -> Policy:
        """The policy a snapshot recorded: its classes, or the vocabulary it
        named among the tree's own; a snapshot naming neither is refused,
        since roles alone cannot give a block back its class."""
        if not isinstance(d, dict):
            raise UnknownLabel("the snapshot carries no policy at all")
        classes = d.get("classes")
        if isinstance(classes, dict) and classes:
            return Policy.from_classes(classes, str(d.get("vocabulary") or ""))
        name = d.get("vocabulary")
        if isinstance(name, str) and name in POLICIES:
            return POLICIES[name]
        raise UnknownLabel(
            f"the snapshot names the vocabulary {name!r}, which this tree "
            f"does not hold, and carries no classes of its own")


# The tree's own vocabularies, label to class. One per adapter family, kept
# apart so a spelling error shows: `Table` from egret is not `table` from V2.
VOCABULARIES: dict[str, dict[str, str]] = {
    "PP-DocLayoutV2": {
        "table": "table", "chart": "chart", "image": "picture",
        "display_formula": "display_formula",
        "header_image": "header_image", "footer_image": "footer_image",
        "seal": "seal",
        "abstract": "text", "algorithm": "algorithm", "aside_text": "text",
        "content": "text", "doc_title": "text", "figure_title": "caption",
        "paragraph_title": "text", "reference": "text",
        "reference_content": "text", "text": "text", "vertical_text": "text",
        "inline_formula": "inline_formula", "formula_number": "text",
        "header": "page_header", "footer": "page_footer",
        "number": "page_footer", "footnote": "footnote",
        "vision_footnote": "footnote",
    },
    # V2's predecessor: twenty classes, one `formula`, no reading order.
    "PP-DocLayout_plus-L": {
        "table": "table", "chart": "chart", "image": "picture",
        "formula": "display_formula", "seal": "seal",
        "abstract": "text", "algorithm": "algorithm", "aside_text": "text",
        "content": "text", "doc_title": "text", "figure_title": "caption",
        "paragraph_title": "text", "reference": "text",
        "reference_content": "text", "text": "text", "formula_number": "text",
        "header": "page_header", "footer": "page_footer",
        "number": "page_footer", "footnote": "footnote",
    },
    # Docling heron (IBM): seventeen classes, and no chart -- charts go to `picture`.
    "Docling": {
        "table": "table", "picture": "picture", "formula": "display_formula",
        "code": "code", "caption": "caption", "list_item": "text",
        "section_header": "text", "text": "text", "title": "text",
        "document_index": "text", "form": "text", "key_value_region": "text",
        "checkbox_selected": "text", "checkbox_unselected": "text",
        "page_header": "page_header", "page_footer": "page_footer",
        "footnote": "footnote",
    },
    # Docling egret (D-FINE): heron's classes spelled otherwise.
    "Docling-egret": {
        "Table": "table", "Picture": "picture", "Formula": "display_formula",
        "Code": "code", "Caption": "caption", "List-item": "text",
        "Section-header": "text", "Text": "text", "Title": "text",
        "Document Index": "text", "Form": "text", "Key-Value Region": "text",
        "Checkbox-Selected": "text", "Checkbox-Unselected": "text",
        "Page-header": "page_header", "Page-footer": "page_footer",
        "Footnote": "footnote",
    },
    # DocLayNet, what the YOLO detectors are trained on: eleven classes.
    "DocLayNet": {
        "Table": "table", "Picture": "picture", "Formula": "display_formula",
        "Caption": "caption", "List-item": "text", "Section-header": "text",
        "Text": "text", "Title": "text",
        "Page-header": "page_header", "Page-footer": "page_footer",
        "Footnote": "footnote",
    },
}

POLICIES: dict[str, Policy] = {n: Policy(n, m) for n, m in VOCABULARIES.items()}


def _union() -> Policy:
    merged: dict[str, str] = {}
    for name, table in VOCABULARIES.items():
        for lab, c in table.items():
            if merged.get(lab, c) != c:
                raise RuntimeError(
                    f"the label {lab!r} means different things in different "
                    f"vocabularies: {merged[lab]!r} and {c!r} in {name}. The "
                    f"union would silently pick one of the two, and a truth "
                    f"block's class would depend on the import order.")
            merged[lab] = c
    return Policy("union", merged)


# Truth's policy until truth declares one: every label of every vocabulary the
# tree's benches are annotated in, and no label meaning two things.
UNION = _union()


def for_labels(labels: Iterable[str]) -> Policy:
    """Which of the tree's own policies describes this vocabulary of labels,
    comparing the sets exactly: a renamed label fits nothing, and none
    fitting is a fall. A served model brings its mapping and never asks."""
    have = set(labels)
    fit = [p for p in POLICIES.values() if set(p.classes) == have]
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise UnknownLabel(
            f"no policy for a vocabulary of {len(have)} labels: "
            f"{sorted(have)[:6]}... Describe it in policy.VOCABULARIES, or "
            f"serve the model with its mapping -- there is no default here "
            f"on purpose.")
    raise UnknownLabel(f"several policies fit this vocabulary: "
                       f"{[p.name for p in fit]}")


def fits(labels: Iterable[str]) -> list[str]:
    """Which of the tree's own vocabularies hold ALL of these labels at once."""
    have = set(labels)
    return sorted(p.name for p in POLICIES.values() if have <= set(p.classes))
