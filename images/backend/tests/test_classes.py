"""Policy completeness: a label absent from the mapping must kill the run"""

import pytest
from backend import classes as policy


def test_check_passes_on_its_own_dictionary():
    for p in policy.POLICIES.values():
        p.check(p.labels)


def test_unknown_label_raises():
    for name, p in policy.POLICIES.items():
        with pytest.raises(policy.UnknownLabel) as e:
            p.check(list(p.labels) + ["Chart_2027"])
        assert "Chart_2027" in str(e.value), f"{name}: the complaint has no label"


def test_label_missing_from_model_also_raises():
    for name, p in policy.POLICIES.items():
        with pytest.raises(policy.UnknownLabel) as e:
            p.check(p.labels[1:])
        assert p.labels[0] in str(e.value), name


def test_a_mapping_onto_an_undeclared_class_is_refused():
    with pytest.raises(policy.UnknownLabel) as e:
        policy.Policy.from_classes({"x": "hologram"})
    assert "hologram" in str(e.value)
    with pytest.raises(policy.UnknownLabel):
        policy.Policy.from_classes({"": "text"})


def test_check_does_not_use_the_union():
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
    for name, p in policy.POLICIES.items():
        for lab in p.labels:
            assert policy.UNION.cls(lab) == p.cls(lab), f"{name}/{lab}"
    assert set(policy.UNION.labels) == set().union(
        *(set(p.labels) for p in policy.POLICIES.values())
    )


def test_for_labels_picks_by_dictionary_not_by_name():
    for name, p in policy.POLICIES.items():
        assert policy.for_labels(p.labels) is p, name
    for bad in (["text", "table"], [], list(policy.UNION.labels)):
        with pytest.raises(policy.UnknownLabel):
            policy.for_labels(bad)
    assert policy.fits(["text", "table"]) == ["Docling", "PP-DocLayoutV2", "PP-DocLayout_plus-L"]


def test_artefacts_are_not_empty_and_are_artefacts():
    arte = policy.UNION.artefacts()
    assert arte, "not one artifact: level two has nothing to cut"
    for lab in arte:
        assert policy.UNION.role(lab) == "artifact"
    assert "table" in arte and "Table" in arte


def test_snapshot_carries_the_whole_mapping_and_comes_back():
    for name, p in policy.POLICIES.items():
        s = p.snapshot()
        assert s["vocabulary"] == name and s["buckets"] == list(policy.ROLES)
        assert s["classes"] == dict(p.classes)
        assert s["by_label"] == {lab: p.role(lab) for lab in p.labels}
        assert policy.Policy.from_snapshot(s) == p
        assert policy.Policy.from_snapshot({"vocabulary": name}) is p
    own = policy.Policy.from_classes({"Grid": "table"})
    assert policy.Policy.from_snapshot(own.snapshot()) == own and own.name == ""
    for bad in (None, {}, {"vocabulary": "PP-DocLayoutV9"}, {"by_label": {"x": "text"}}):
        with pytest.raises(policy.UnknownLabel):
            policy.Policy.from_snapshot(bad)


