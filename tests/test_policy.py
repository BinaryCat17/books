"""Policy completeness: a label absent from the dictionary must kill the run.

"THE POLICY IS COMPLETE BY CONSTRUCTION, AND THAT IS THE MAIN THING IN THE
FILE" says `policy.py`, and its price is known: in the paddlex postprocessing
a threshold dictionary with one class silently gave the rest 0.5. The
twenty-sixth class of new weights would spill into the prose under a default
-- "artefacts 40" becoming "artefacts 39", unnoticed.

Both sides are checked: the policy knows the model's dictionary WHOLE, and the
dictionary knows the policy. Five dictionaries at five detectors, not to be
muddled: `check` compares against ONE named dictionary, not their union.
"""
from booksmith import policy
from booksmith.models import docling_heron, yolox_layout


def test_check_passes_on_its_own_dictionary():
    for name, table in policy.POLICIES.items():
        policy.check(list(table), name)      # silent means it agreed


def test_unknown_label_raises():
    """A spare model label: a fall naming the label, not a quiet default."""
    for name, table in policy.POLICIES.items():
        try:
            policy.check(list(table) + ["Chart_2027"], name)
        except policy.UnknownLabel as e:
            assert "Chart_2027" in str(e), f"the complaint has no label: {e}"
        else:
            raise AssertionError(
                f"policy {name} swallowed an unknown label: it would "
                f"silently travel into the prose and the artifact count would "
                f"fall without a word")


def test_label_missing_from_model_also_raises():
    """And back: `figure` for `image` would mean "artefacts 0" for ever."""
    for name, table in policy.POLICIES.items():
        labels = sorted(table)[1:]
        try:
            policy.check(labels, name)
        except policy.UnknownLabel as e:
            assert sorted(table)[0] in str(e)
        else:
            raise AssertionError(
                f"policy {name} describes a label the model does not have "
                f"and keeps quiet: a typo here shows in nothing but a "
                f"permanent zero")


def test_unknown_policy_name_raises():
    try:
        policy.check(["text"], "PP-DocLayoutV9")
    except policy.UnknownLabel as e:
        assert "PP-DocLayoutV9" in str(e)
    else:
        raise AssertionError("a policy with an invented name was accepted")


def test_check_does_not_use_the_union():
    """The check is against the named dictionary, not the union of all five.

    The union covers foreign labels too, and the check would stop catching
    what it was written for: `Table` from DocLayNet in a V2 run means swapped
    weights, not a lawful label.
    """
    try:
        policy.check(list(policy.PP_DOCLAYOUT_V2) + ["Table"], "PP-DocLayoutV2")
    except policy.UnknownLabel:
        pass
    else:
        raise AssertionError(
            "a foreign label from another vocabulary passed the check: the "
            "comparison is against the union, and swapped weights will pass "
            "in silence")


def test_role_raises_on_unknown():
    try:
        policy.role("an_invented_label")
    except policy.UnknownLabel:
        pass
    else:
        raise AssertionError("`role` gave a role to a label it does not know")


def test_every_label_has_one_of_three_roles():
    assert policy.ROLES == ("text", "artifact", "furniture")
    for name, table in policy.POLICIES.items():
        for lab, r in table.items():
            assert r in policy.ROLES, f"{name}/{lab}: role {r!r} is not one of three"


def test_union_agrees_with_every_dictionary():
    """`ROLE` is the union with a contradiction check, and it is alive.

    One label cannot mean different things in two dictionaries: `formula` is
    an artefact in both, and a role cannot depend on import order.
    """
    for name, table in policy.POLICIES.items():
        for lab, r in table.items():
            assert policy.ROLE[lab] == r, (
                f"{name}/{lab}: {policy.ROLE[lab]!r} in the union, in the vocabulary "
                f"{r!r}")
    assert set(policy.ROLE) == set().union(*(set(t) for t in
                                             policy.POLICIES.values()))


def test_for_labels_picks_by_dictionary_not_by_name():
    """The policy is picked by DICTIONARY: a weights name can be muddled."""
    for name, table in policy.POLICIES.items():
        assert policy.for_labels(list(table)) == name
    for bad in (["text", "table"], [], list(policy.ROLE)):
        try:
            policy.for_labels(bad)
        except policy.UnknownLabel:
            pass
        else:
            raise AssertionError(
                f"a policy was found for a vocabulary of {len(bad)} labels: "
                f"it can match none")


def test_adapters_and_policies_agree():
    """An agreement through a file: adapter dictionary -> policy name.

    `detect.py` calls `policy.check` with the model's dictionary; diverge
    here and the adapter's run would fall on its own bench.
    """
    pairs = ((docling_heron.DoclingHeron, list(docling_heron.DEFAULT_LABELS)),
             (docling_heron.DoclingEgret,
              list(docling_heron.EGRET_TO_DOCLING)),
             (yolox_layout.YoloXLayout, list(yolox_layout.LABELS)))
    for cls, labels in pairs:
        assert cls.policy_name in policy.POLICIES, (
            f"{cls.__name__}.policy_name = {cls.policy_name!r}, and there "
            f"is no such policy")
        assert policy.for_labels(labels) == cls.policy_name, (
            f"{cls.__name__}: the label vocabulary points at policy "
            f"{policy.for_labels(labels)!r}, and {cls.policy_name!r} is "
            f"declared")
        policy.check(labels, cls.policy_name)


def test_artefacts_are_not_empty_and_are_artefacts():
    """An empty artefact list would silently turn the book into solid text."""
    arte = policy.artefacts()
    assert arte, "not one artifact: level two has nothing to cut"
    for lab in arte:
        assert policy.ROLE[lab] == "artifact"
    assert "table" in arte and "Table" in arte


def test_snapshot_carries_whole_dictionary():
    """The snapshot carries the whole policy: else the count means nothing."""
    for name, table in policy.POLICIES.items():
        s = policy.snapshot(name)
        assert s["vocabulary"] == name
        assert s["by_label"] == dict(sorted(table.items())), (
            f"the policy snapshot for {name} is incomplete: "
            f"{len(s['by_label'])} labels of {len(table)}")
    whole = policy.snapshot()
    assert sorted(whole["vocabularies"]) == sorted(policy.POLICIES)
    assert len(whole["by_label"]) == len(policy.ROLE)
