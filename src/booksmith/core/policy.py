"""What level one does with a block: `text`, `artifact` or `furniture`.

Ours, not the model's: declared whole and carried into the snapshot, or "40
artifacts" cannot be read back. The policy is complete by construction -- a
label absent from here fells the run, and there is no default, so new weights
with one more class cannot pour it into the prose unnoticed.

`artifact` is cut out as a picture for level two to take apart, `text` stays
text in the flow, and `furniture` -- running heads, folios, footnotes -- is
text most likely unwanted, marked and kept until the bench decides.
"""

from booksmith.core.errors import Unmeasurable
# One policy per label vocabulary; `ROLE` is their union, and a label may not mean two things.
PP_DOCLAYOUT_V2 = {
    # --- cut out as a picture ------------------------------------------
    "table": "artifact",
    "chart": "artifact",
    "image": "artifact",
    # A formula as a block is a picture; whether it becomes HTML is level two's business.
    "display_formula": "artifact",
    "header_image": "artifact",
    "footer_image": "artifact",
    "seal": "artifact",

    # --- stays text ----------------------------------------------------
    "abstract": "text",
    "algorithm": "text",
    "aside_text": "text",
    "content": "text",
    "doc_title": "text",
    "figure_title": "text",
    "paragraph_title": "text",
    "reference": "text",
    "reference_content": "text",
    "text": "text",
    "vertical_text": "text",
    # Text, not a picture: cutting an inline formula out would tear the sentence in half.
    "inline_formula": "text",
    "formula_number": "text",

    # --- furniture: marked, not thrown away ------------------------------
    "header": "furniture",
    "footer": "furniture",
    "number": "furniture",
    "footnote": "furniture",
    "vision_footnote": "furniture",
}

# DocLayNet, what the YOLO detectors are trained on: eleven classes, one formula, no order.
DOCLAYNET = {
    "Table": "artifact",
    "Picture": "artifact",
    "Formula": "artifact",
    "Caption": "text",
    "List-item": "text",
    "Section-header": "text",
    "Text": "text",
    "Title": "text",
    "Page-header": "furniture",
    "Page-footer": "furniture",
    "Footnote": "furniture",
}

# Docling heron/egret (IBM): seventeen classes, and no `chart` -- charts go to `picture`.
DOCLING = {
    "table": "artifact",
    "picture": "artifact",
    "formula": "artifact",
    "code": "artifact",
    "caption": "text",
    "list_item": "text",
    "section_header": "text",
    "text": "text",
    "title": "text",
    "document_index": "text",
    "form": "text",
    "key_value_region": "text",
    "checkbox_selected": "text",
    "checkbox_unselected": "text",
    "page_header": "furniture",
    "page_footer": "furniture",
    "footnote": "furniture",
}

# PP-DocLayout_plus-L, V2's predecessor: twenty classes, one `formula`, no reading order.
PP_DOCLAYOUT_PLUS_L = {
    "table": "artifact",
    "chart": "artifact",
    "image": "artifact",
    "formula": "artifact",
    "seal": "artifact",
    "abstract": "text",
    "algorithm": "text",
    "aside_text": "text",
    "content": "text",
    "doc_title": "text",
    "figure_title": "text",
    "paragraph_title": "text",
    "reference": "text",
    "reference_content": "text",
    "text": "text",
    "formula_number": "text",
    "header": "furniture",
    "footer": "furniture",
    "number": "furniture",
    "footnote": "furniture",
}

# Docling egret (D-FINE): heron's classes spelled otherwise, kept apart so a naming error shows.
DOCLING_EGRET = {
    "Table": "artifact",
    "Picture": "artifact",
    "Formula": "artifact",
    "Code": "artifact",
    "Caption": "text",
    "List-item": "text",
    "Section-header": "text",
    "Text": "text",
    "Title": "text",
    "Document Index": "text",
    "Form": "text",
    "Key-Value Region": "text",
    "Checkbox-Selected": "text",
    "Checkbox-Unselected": "text",
    "Page-header": "furniture",
    "Page-footer": "furniture",
    "Footnote": "furniture",
}

POLICIES = {
    "PP-DocLayoutV2": PP_DOCLAYOUT_V2,
    "Docling-egret": DOCLING_EGRET,
    "PP-DocLayout_plus-L": PP_DOCLAYOUT_PLUS_L,
    "DocLayNet": DOCLAYNET,
    "Docling": DOCLING,
}

ROLE: dict[str, str] = {}
for _name, _table in POLICIES.items():
    for _lab, _r in _table.items():
        if ROLE.get(_lab, _r) != _r:
            raise RuntimeError(
                f"the label {_lab!r} means different things in different "
                f"vocabularies: {ROLE[_lab]!r} and {_r!r}. The union would "
                f"silently pick one of the two, and a block's role would "
                f"depend on the import order.")
        ROLE[_lab] = _r

ROLES = ("text", "artifact", "furniture")


class UnknownLabel(Unmeasurable):
    """The model's label is not described by the policy. Fell, do not guess."""


def check(labels, policy: str = "PP-DocLayoutV2") -> None:
    """The policy must cover the model's vocabulary whole, and hold nothing extra.

    Checked every run, the vocabulary arriving with the weights, and against one
    named vocabulary rather than the union, which covers foreign labels too.
    """
    if policy not in POLICIES:
        raise UnknownLabel(
            f"no policy {policy!r}: there are {sorted(POLICIES)}")
    have, mine = set(labels), set(POLICIES[policy])
    if have - mine:
        raise UnknownLabel(
            f"the policy does not describe the model's labels: "
            f"{sorted(have - mine)}. Describe them in "
            f"policy.POLICIES[{policy!r}] -- there is no default here on "
            f"purpose. Adding to policy.ROLE will NOT help: it is derived "
            f"from POLICIES.")
    if mine - have:
        raise UnknownLabel(
            f"the policy describes labels the model does not have: "
            f"{sorted(mine - have)}. A typo here shows in nothing but an "
            f"eternal zero in the report.")


def for_labels(labels) -> str:
    """Which policy describes this vocabulary of labels.

    Chosen by the model's own class list rather than a name we typed, comparing
    the sets exactly: a renamed label fits nothing, and none fitting is a fall.
    """
    have = set(labels)
    fit = [n for n, t in POLICIES.items() if set(t) == have]
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise UnknownLabel(
            f"no policy for a vocabulary of {len(have)} labels: "
            f"{sorted(have)[:6]}... Describe it in policy.POLICIES -- there "
            f"is no default here on purpose.")
    raise UnknownLabel(f"several policies fit this vocabulary: {fit}")


def role(label: str) -> str:
    try:
        return ROLE[label]
    except KeyError:
        raise UnknownLabel(
            f"the label {label!r} is not described by the policy") from None


def artefacts() -> tuple[str, ...]:
    return tuple(sorted(l for l, r in ROLE.items() if r == "artifact"))


def snapshot(policy: str | None = None) -> dict:
    """The policy whole, into the snapshot."""
    if policy:
        return {"buckets": list(ROLES), "vocabulary": policy,
                "by_label": dict(sorted(POLICIES[policy].items()))}
    return {"buckets": list(ROLES), "vocabularies": sorted(POLICIES),
            "by_label": dict(sorted(ROLE.items()))}
