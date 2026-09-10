"""Policy completeness: a label absent from the mapping must kill the run.

A policy is a model's labels onto the classes, complete by construction, and
the price of a default is known: a threshold dictionary with one class
silently gave the rest 0.5, and a new class of weights would spill into the
prose as one artefact fewer. Both sides are checked: the policy knows the
model's dictionary whole, and the dictionary knows the policy. Five
vocabularies of the tree's own, not to be muddled -- `check` compares against
one named mapping, never their union -- and one table of classes that must
reproduce the three tables it replaced.
"""
import json
import os

import pytest

from booksmith.core import config, policy
from booksmith.processing.layout.adapters import (
    docling as docling_heron,
    yolox as yolox_layout)
from booksmith.processing.read.readers import paddleocr_vl as reader


def test_check_passes_on_its_own_dictionary():
    for p in policy.POLICIES.values():
        p.check(p.labels)                    # silent means it agreed


def test_unknown_label_raises():
    """A spare model label: a fall naming the label, not a quiet default."""
    for name, p in policy.POLICIES.items():
        with pytest.raises(policy.UnknownLabel) as e:
            p.check(list(p.labels) + ["Chart_2027"])
        assert "Chart_2027" in str(e.value), f"{name}: the complaint has no label"


def test_label_missing_from_model_also_raises():
    """And back: `figure` for `image` would mean "artefacts 0" for ever."""
    for name, p in policy.POLICIES.items():
        with pytest.raises(policy.UnknownLabel) as e:
            p.check(p.labels[1:])
        assert p.labels[0] in str(e.value), name


def test_a_mapping_onto_an_undeclared_class_is_refused():
    """A served model may say anything of its labels; a class the tree does
    not declare has no role and no order name, and is refused by name."""
    with pytest.raises(policy.UnknownLabel) as e:
        policy.Policy.from_classes({"x": "hologram"})
    assert "hologram" in str(e.value)
    with pytest.raises(policy.UnknownLabel):
        policy.Policy.from_classes({"": "text"})


def test_check_does_not_use_the_union():
    """`Table` from DocLayNet in a V2 run means swapped weights, not a lawful
    label: the comparison is against the named mapping, not the union."""
    v2 = policy.POLICIES["PP-DocLayoutV2"]
    with pytest.raises(policy.UnknownLabel):
        v2.check(list(v2.labels) + ["Table"])
    assert policy.UNION.role("Table") == "artifact", "the union knows it"


def test_role_raises_on_unknown():
    with pytest.raises(policy.UnknownLabel):
        policy.UNION.role("an_invented_label")
    with pytest.raises(policy.UnknownLabel):
        policy.POLICIES["Docling"].cls("table_of_contents")


def test_every_class_has_one_of_three_roles_and_a_name_the_rules_read():
    assert policy.ROLES == ("text", "artifact", "furniture")
    for c, (role, order_name) in policy.CLASSES.items():
        assert role in policy.ROLES, f"{c}: role {role!r} is not one of three"
        assert order_name in policy.ORDER_NAMES, f"{c}: {order_name!r}"
    assert len(policy.CLASSES) == 15


def test_union_agrees_with_every_dictionary():
    """The union is the five with a contradiction check: one label cannot
    mean two classes, and a truth block's class cannot depend on import order."""
    for name, p in policy.POLICIES.items():
        for lab in p.labels:
            assert policy.UNION.cls(lab) == p.cls(lab), f"{name}/{lab}"
    assert set(policy.UNION.labels) == set().union(
        *(set(p.labels) for p in policy.POLICIES.values()))


def test_for_labels_picks_by_dictionary_not_by_name():
    for name, p in policy.POLICIES.items():
        assert policy.for_labels(p.labels) is p, name
    for bad in (["text", "table"], [], list(policy.UNION.labels)):
        with pytest.raises(policy.UnknownLabel):
            policy.for_labels(bad)
    assert policy.fits(["text", "table"]) == ["Docling", "PP-DocLayoutV2",
                                              "PP-DocLayout_plus-L"]


def test_adapters_and_policies_agree():
    """An agreement through a file: adapter dictionary -> policy name.
    `detect.py` checks the adapter's policy against the model's dictionary,
    so a divergence here drops the adapter's run on its own bench."""
    pairs = ((docling_heron.DoclingHeron, list(docling_heron.DEFAULT_LABELS)),
             (docling_heron.DoclingEgret, list(docling_heron.EGRET_TO_DOCLING)),
             (yolox_layout.YoloXLayout, list(yolox_layout.LABELS)))
    for cls, labels in pairs:
        assert cls.policy_name in policy.POLICIES, (
            f"{cls.__name__}.policy_name = {cls.policy_name!r}, and there "
            f"is no such policy")
        assert policy.for_labels(labels).name == cls.policy_name, cls.__name__
        policy.POLICIES[cls.policy_name].check(labels)


def test_artefacts_are_not_empty_and_are_artefacts():
    """An empty artefact list would silently turn the book into solid text."""
    arte = policy.UNION.artefacts()
    assert arte, "not one artifact: level two has nothing to cut"
    for lab in arte:
        assert policy.UNION.role(lab) == "artifact"
    assert "table" in arte and "Table" in arte


def test_snapshot_carries_the_whole_mapping_and_comes_back():
    """The snapshot carries the mapping whole, and the roles beside it for a
    reader of buckets; a policy read back is the policy."""
    for name, p in policy.POLICIES.items():
        s = p.snapshot()
        assert s["vocabulary"] == name and s["buckets"] == list(policy.ROLES)
        assert s["classes"] == dict(p.classes)
        assert s["by_label"] == {lab: p.role(lab) for lab in p.labels}
        assert policy.Policy.from_snapshot(s) == p
        assert policy.Policy.from_snapshot({"vocabulary": name}) is p
    own = policy.Policy.from_classes({"Grid": "table"})
    assert policy.Policy.from_snapshot(own.snapshot()) == own and own.name == ""
    for bad in (None, {}, {"vocabulary": "PP-DocLayoutV9"},
                {"by_label": {"x": "text"}}):
        with pytest.raises(policy.UnknownLabel):
            policy.Policy.from_snapshot(bad)


def test_the_classes_reproduce_the_three_tables_they_replaced():
    """One table of classes stands where a policy table, an order translation
    and a route table stood, each keyed by vocabulary. The lock is those
    three as they were, label by label: role, order name, prompt and kind."""
    with open(os.path.join(config.ROOT, "tests", "expected",
                           "classes-before.json"), encoding="utf-8") as f:
        before = json.load(f)
    assert set(before) == set(policy.POLICIES)
    for name, labels in before.items():
        p = policy.POLICIES[name]
        assert set(labels) == set(p.labels), name
        for lab, want in labels.items():
            rt = reader.ROUTES[p.cls(lab)]
            got = {"role": p.role(lab), "order_name": p.order_name(lab),
                   "prompt": rt.prompt, "kind": rt.kind}
            assert got == want, f"{name}/{lab}: {got} was {want}"
    assert set(reader.ROUTES) == set(policy.CLASSES), "a class with no route"
