"""What level one does with a block: `text`, `artifact` or `furniture`.

OURS, not the model's, and so declared outright, whole, and carried into the
snapshot: "40 artifacts" cannot be read back without it, short of opening the
same commit.

THE POLICY IS COMPLETE BY CONSTRUCTION, AND THAT IS THE POINT OF THE FILE. A
label absent from here fells the run. No default, deliberately: in the paddlex
postprocessing a threshold dict holding one class silently gave the rest 0.5,
so "lower the table threshold" changed the behaviour of all twenty-five. The
same trap waits here: new weights with a twenty-sixth class would pour it into
the prose without a word.

THREE ROLES, NOT TWO. `artifact` is cut out as a picture and inserted as is;
level two takes it apart, in isolation from its neighbours. `text` stays text
in the flow. `furniture` -- running heads, folios, footnotes -- is formally
text and most likely unwanted, but dropping it NOW is a decision without a
measurement, so it is marked and kept: the mark costs nothing, the dropped
could not be restored. The bench decides.
"""

# SEVERAL POLICIES -- one per LABEL VOCABULARY. With one detector the policy
# was one, and "is another model better" could not even be measured: a foreign
# label felled the run. Now each vocabulary is declared apart and whole, and
# `ROLE` is their union with a contradiction check -- one label cannot mean
# two things in two vocabularies.
PP_DOCLAYOUT_V2 = {
    # --- cut out as a picture ------------------------------------------
    "table": "artifact",
    "chart": "artifact",
    "image": "artifact",
    # A formula as a block is a picture. It goes to HTML badly and not always,
    # and deciding that is level two's business, not ours.
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
    # CAREFUL, A BORDERLINE CASE. An inline formula lives INSIDE the flow, and
    # cutting it out as a picture tears a sentence in half. So text -- with a
    # caveat: the content is then lost silently while every contour number
    # stays perfect. First candidate for a measurement.
    "inline_formula": "text",
    "formula_number": "text",

    # --- furniture: marked, not thrown away ------------------------------
    "header": "furniture",
    "footer": "furniture",
    "number": "furniture",
    "footnote": "furniture",
    "vision_footnote": "furniture",
}

# DocLayNet -- the vocabulary the YOLO layout detectors are trained on
# (yolov10/11 doclaynet, DocLayout-YOLO). Eleven classes against our
# twenty-five: one formula here for every kind, and no reading order at all.
# Declared so the architectures can be compared at all.
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

# Docling heron/egret (IBM): seventeen classes, RT-DETRv2 on other data.
# Declared for the CROSS-CHECK: two independent models on the same pages
# answer whether merging is a property of the architecture or of the sample.
# It has NO `chart` class -- charts go to `picture`, to be remembered when
# comparing: our `chart` is inexpressible to it.
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

# PP-DocLayout_plus-L -- V2's predecessor in the same family: twenty classes
# instead of twenty-five, ONE `formula` for display and inline both, and NO
# reading order (V2's pointer network brought that). Declared to measure the
# pedigree: what the five added classes and the pointer network gave.
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

# Docling egret (D-FINE): the same seventeen classes as heron, but the names
# are spelled otherwise -- capitalised and hyphenated. A separate policy, not
# a merge: merging would erase the difference of the vocabularies, our only
# way to tell a translation error from a model error.
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
                f"ярлык {_lab!r} значит в разных словарях разное: "
                f"{ROLE[_lab]!r} и {_r!r}. Объединение тут молча выбрало бы "
                f"одно из двух, и разряд блока зависел бы от порядка импорта.")
        ROLE[_lab] = _r

ROLES = ("text", "artifact", "furniture")


class UnknownLabel(RuntimeError):
    """The model's label is not described by the policy. Fell, do not guess."""


def check(labels, policy: str = "PP-DocLayoutV2") -> None:
    """The policy must cover the model's vocabulary WHOLE.

    Checked every run, not once: the vocabulary arrives with the weights, and
    changing weights is the likeliest way to acquire a twenty-sixth class.
    Something extra in the policy is trouble too: `"figure"` instead of
    `"image"` would give "artifacts 0" for ever and silently.

    Compared against ONE named vocabulary, not the union: the union covers
    foreign labels too, and the check would stop catching what it is for.
    """
    if policy not in POLICIES:
        raise UnknownLabel(f"нет политики {policy!r}: есть {sorted(POLICIES)}")
    have, mine = set(labels), set(POLICIES[policy])
    if have - mine:
        raise UnknownLabel(
            f"политика не описывает ярлыки модели: {sorted(have - mine)}. "
            f"Опишите их в policy.POLICIES[{policy!r}] — умолчания здесь нет нарочно. Дописать в policy.ROLE НЕ поможет: она из POLICIES и выводится.")
    if mine - have:
        raise UnknownLabel(
            f"политика описывает ярлыки, которых нет у модели: "
            f"{sorted(mine - have)}. Опечатка тут не видна ничем, кроме "
            f"вечного нуля в отчёте.")


def for_labels(labels) -> str:
    """Which policy describes THIS vocabulary of labels.

    Chosen by the MODEL'S VOCABULARY, not a name we typed out: a weights
    name can be mistaken, the class list arrives from the weights
    themselves. The SETS are compared exactly -- rename one label and no
    policy fits any more. None fitting is a fall; two fitting does not happen,
    the class sets of our models being distinct.
    """
    have = set(labels)
    fit = [n for n, t in POLICIES.items() if set(t) == have]
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise UnknownLabel(
            f"нет политики под словарь из {len(have)} ярлыков: "
            f"{sorted(have)[:6]}… Опишите его в policy.POLICIES — умолчания "
            f"здесь нет нарочно.")
    raise UnknownLabel(f"под этот словарь подходит несколько политик: {fit}")


def role(label: str) -> str:
    try:
        return ROLE[label]
    except KeyError:
        raise UnknownLabel(f"ярлык {label!r} не описан политикой") from None


def artefacts() -> tuple[str, ...]:
    return tuple(sorted(l for l, r in ROLE.items() if r == "artifact"))


def snapshot(policy: str | None = None) -> dict:
    """The policy whole, into the snapshot."""
    if policy:
        return {"buckets": list(ROLES), "vocabulary": policy,
                "by_label": dict(sorted(POLICIES[policy].items()))}
    return {"buckets": list(ROLES), "vocabularies": sorted(POLICIES),
            "by_label": dict(sorted(ROLE.items()))}
