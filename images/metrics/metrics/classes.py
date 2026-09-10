"""What level one does with a block: `text`, `artifact` or `furniture`, by class"""

from __future__ import annotations
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from metrics.errors import Unmeasurable

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
CLASSES: dict[str, tuple[str, str]] = {
    "text": ("text", "text"),
    "caption": ("text", "caption"),
    "algorithm": ("text", "code"),
    "inline_formula": ("text", "text"),
    "code": ("artifact", "code"),
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
        if not all((isinstance(lab, str) and lab for lab in self.classes)):
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
        return tuple(sorted((lab for lab in self.classes if CLASSES[self.classes[lab]][0] == role)))

    def covers(self, labels: Iterable[str]) -> bool:
        return set(labels) <= set(self.classes)

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


VOCABULARIES: dict[str, dict[str, str]] = {
    "PP-DocLayoutV2": {
        "table": "table",
        "chart": "chart",
        "image": "picture",
        "display_formula": "display_formula",
        "header_image": "header_image",
        "footer_image": "footer_image",
        "seal": "seal",
        "abstract": "text",
        "algorithm": "algorithm",
        "aside_text": "text",
        "content": "text",
        "doc_title": "text",
        "figure_title": "caption",
        "paragraph_title": "text",
        "reference": "text",
        "reference_content": "text",
        "text": "text",
        "vertical_text": "text",
        "inline_formula": "inline_formula",
        "formula_number": "text",
        "header": "page_header",
        "footer": "page_footer",
        "number": "page_footer",
        "footnote": "footnote",
        "vision_footnote": "footnote",
    },
    "PP-DocLayout_plus-L": {
        "table": "table",
        "chart": "chart",
        "image": "picture",
        "formula": "display_formula",
        "seal": "seal",
        "abstract": "text",
        "algorithm": "algorithm",
        "aside_text": "text",
        "content": "text",
        "doc_title": "text",
        "figure_title": "caption",
        "paragraph_title": "text",
        "reference": "text",
        "reference_content": "text",
        "text": "text",
        "formula_number": "text",
        "header": "page_header",
        "footer": "page_footer",
        "number": "page_footer",
        "footnote": "footnote",
    },
    "Docling": {
        "table": "table",
        "picture": "picture",
        "formula": "display_formula",
        "code": "code",
        "caption": "caption",
        "list_item": "text",
        "section_header": "text",
        "text": "text",
        "title": "text",
        "document_index": "text",
        "form": "text",
        "key_value_region": "text",
        "checkbox_selected": "text",
        "checkbox_unselected": "text",
        "page_header": "page_header",
        "page_footer": "page_footer",
        "footnote": "footnote",
    },
    "Docling-egret": {
        "Table": "table",
        "Picture": "picture",
        "Formula": "display_formula",
        "Code": "code",
        "Caption": "caption",
        "List-item": "text",
        "Section-header": "text",
        "Text": "text",
        "Title": "text",
        "Document Index": "text",
        "Form": "text",
        "Key-Value Region": "text",
        "Checkbox-Selected": "text",
        "Checkbox-Unselected": "text",
        "Page-header": "page_header",
        "Page-footer": "page_footer",
        "Footnote": "footnote",
    },
    "DocLayNet": {
        "Table": "table",
        "Picture": "picture",
        "Formula": "display_formula",
        "Caption": "caption",
        "List-item": "text",
        "Section-header": "text",
        "Text": "text",
        "Title": "text",
        "Page-header": "page_header",
        "Page-footer": "page_footer",
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
    return sorted((p.name for p in POLICIES.values() if have <= set(p.classes)))
