"""The metric's pairs as data: one entry per truth block with the verdict the
count gave it, every run box neither pass took with what the count calls it,
and a page that says it is not labelled left out of the count and said so.
The sheet and the viewer draw from this list; the record does not carry it."""
import copy

import pytest

import support
from booksmith.core import page as page_mod
from booksmith.core import policy
from booksmith.datasets.metrics import contour
from fake_layout import truth_pages


def _model_of(T):
    """Truth as a model would return it: no provenance, no content."""
    M = copy.deepcopy(T)
    for p in M.values():
        for b in p["blocks"]:
            b.pop("source_category", None)
            b["content"], b["kind"] = None, "none"
        p["meta"] = {"reading_order": "own"}
    return M


def _anchors(i, blocks):
    return [page_mod.anchor(i, b["block_id"]) for b in blocks]


def test_truth_against_itself_pairs_every_block_and_the_record_keeps_none_of_it(slovar):
    T = truth_pages(slovar.truth_dir)
    M = _model_of(T)
    res = contour.compare_pages(T, M)
    assert set(res["pairs"]) == set(T)
    for i, t in T.items():
        got = res["pairs"][i]
        assert [e["truth"] for e in got["pairs"]] == _anchors(i, t["blocks"])
        assert all(e["verdict"] == "matched" and e["label_ok"] for e in got["pairs"])
        assert got["extras"] == []
        for e, b in zip(got["pairs"], t["blocks"], strict=True):
            arte = policy.UNION.role(b["label"]) == "artifact"
            assert e["by"] == ("A" if arte else "B"), (e, b["label"])
            assert e["fate"] == ("intact" if arte else None)
            assert e["run"] == e["truth"] and e["why"] is None
        # One page asked alone answers what the whole comparison said of it.
        assert contour.page_pairs(t, M[i]) == got
    rec = contour.ContourMetric().record(res, "slovar", "truth")
    assert "pairs" not in rec.detail, "the record grew a pair per truth block"
    assert rec.detail["labelled"] == {"yes": 0, "no": 0, "not_said": len(T)}


def test_a_lost_block_an_extra_box_and_a_renamed_one_are_said_as_the_count_says(slovar):
    T = truth_pages(slovar.truth_dir)
    M = _model_of(T)
    i, art, txt = next(
        (i, a, x) for i, t in T.items()
        for a in [next((b for b in t["blocks"]
                        if policy.UNION.role(b["label"]) == "artifact"), None)]
        for x in [next((b for b in t["blocks"]
                        if policy.UNION.role(b["label"]) == "text"), None)]
        if a is not None and x is not None)
    m = M[i]
    # Lost: the artefact is gone from the model's page.
    m["blocks"] = [b for b in m["blocks"] if b["block_id"] != art["block_id"]]
    # Renamed: the text block under another name of the same role.
    other = next(lb for lb in policy.UNION.labels
                 if policy.UNION.role(lb) == "text" and lb != txt["label"])
    for b in m["blocks"]:
        if b["block_id"] == txt["block_id"]:
            b["label"] = other
    # Extra: an artefact box where truth has nothing.
    w, h = T[i]["width"], T[i]["height"]
    taken = [b["box"] for b in T[i]["blocks"]]
    spot = next(c for c in ([w - 70, h - 70, w - 10, h - 10], [10, h - 70, 70, h - 10],
                            [w - 70, 10, w - 10, 70], [10, 10, 70, 70])
                if not any(c[0] < bx[2] and bx[0] < c[2] and c[1] < bx[3] and bx[1] < c[3]
                           for bx in taken))
    extra_id = max(b["block_id"] for b in m["blocks"]) + 1
    m["blocks"].append({"block_id": extra_id, "box": spot, "label": art["label"],
                        "score": 0.5, "order": None, "content": None, "kind": "none"})
    res = contour.compare_pages(T, M)
    got = res["pairs"][i]
    by_truth = {e["truth"]: e for e in got["pairs"]}
    lost = by_truth[page_mod.anchor(i, art["block_id"])]
    assert lost["verdict"] == "missed" and lost["by"] == "A" and lost["run"] is None
    assert lost["why"] and lost["fate"] == "not_seen"
    assert f"{lost['why']} ({art['label']})" in res["troubles"]
    renamed = by_truth[page_mod.anchor(i, txt["block_id"])]
    assert renamed["verdict"] == "matched" and renamed["label_ok"] is False
    assert renamed["run"] in res["per"]["label_errors"]
    extra = [e for e in got["extras"] if e["run"] == page_mod.anchor(i, extra_id)]
    assert extra == [{"run": page_mod.anchor(i, extra_id), "verdict": "spurious_box"}]
    assert res["troubles"]["spurious_box"] == 1, "the list and the count disagree"
    # Every model box is in the list exactly once, matched or extra.
    runs = [e["run"] for e in got["pairs"] if e["run"]] + [e["run"] for e in got["extras"]]
    assert sorted(runs) == sorted(_anchors(i, m["blocks"]))
    # The number is the list: found is the matched-by-A count over the book.
    assert res["totals"]["found"] == sum(
        1 for p in res["pairs"].values() for e in p["pairs"]
        if e["by"] == "A" and e["verdict"] == "matched")


def test_a_page_that_says_it_is_not_labelled_is_left_out_and_said(slovar):
    T = truth_pages(slovar.truth_dir)
    M = _model_of(T)
    T[0]["meta"]["labelled"] = False
    T[1]["meta"]["labelled"] = True
    res = contour.compare_pages(T, M)
    assert res["labelled"] == {"yes": 1, "no": 1, "not_said": len(T) - 2}
    assert list(res["pairs"]) == [1], "a page that did not say was compared"
    assert res["text_and_furniture"]["pages_total"] == 1
    assert res["sense"]["objects"] == sum(
        1 for b in T[1]["blocks"] if policy.UNION.role(b["label"]) == "artifact")
    assert contour.page_pairs(T[0], M[0]) is None
    assert contour.page_pairs(T[1], M[1]) == res["pairs"][1]
    with support.said() as said:
        contour.report(res)
    assert any("yes 1, no 1" in ln and "only the pages that say yes" in ln for ln in said)
    for t in T.values():
        t["meta"]["labelled"] = False
    with pytest.raises(contour.MetricError, match="not a zero"):
        contour.compare_pages(T, M)
