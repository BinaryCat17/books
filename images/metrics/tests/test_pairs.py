"""The metric's pairs as data: one entry per truth block with the verdict the"""

import copy
import pytest
import support
from metrics import page as page_mod
from metrics import classes as policy
from metrics import contour
from fake_layout import truth_pages


def _model_of(T):
    M = copy.deepcopy(T)
    for p in M.values():
        for b in p["blocks"]:
            b.pop("source_category", None)
            b["content"], b["kind"] = (None, "none")
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
        assert all((e["verdict"] == "matched" and e["label_ok"] for e in got["pairs"]))
        assert got["extras"] == []
        for e, b in zip(got["pairs"], t["blocks"], strict=True):
            arte = policy.UNION.role(b["label"]) == "artifact"
            assert e["by"] == ("A" if arte else "B"), (e, b["label"])
            assert e["fate"] == ("intact" if arte else None)
            assert e["run"] == e["truth"] and e["why"] is None
            assert e["b_run"] == e["truth"] and e["b_label_ok"] is True
        assert contour.page_pairs(t, M[i]) == got
    rec = contour.ContourMetric().record(res, "slovar", "truth")
    assert "pairs" not in rec.detail, "the record grew a pair per truth block"
    assert rec.detail["labelled"] == {"yes": 0, "no": 0, "not_said": len(T)}


def test_a_lost_block_an_extra_box_and_a_renamed_one_are_said_as_the_count_says(slovar):
    T = truth_pages(slovar.truth_dir)
    M = _model_of(T)
    i, art, txt = next(
        (
            (i, a, x)
            for i, t in T.items()
            for a in [
                next((b for b in t["blocks"] if policy.UNION.role(b["label"]) == "artifact"), None)
            ]
            for x in [
                next((b for b in t["blocks"] if policy.UNION.role(b["label"]) == "text"), None)
            ]
            if a is not None and x is not None
        )
    )
    m = M[i]
    m["blocks"] = [b for b in m["blocks"] if b["block_id"] != art["block_id"]]
    other = next(
        (lb for lb in policy.UNION.labels if policy.UNION.role(lb) == "text" and lb != txt["label"])
    )
    for b in m["blocks"]:
        if b["block_id"] == txt["block_id"]:
            b["label"] = other
    w, h = (T[i]["width"], T[i]["height"])
    taken = [b["box"] for b in T[i]["blocks"]]
    spot = next(
        (
            c
            for c in (
                [w - 70, h - 70, w - 10, h - 10],
                [10, h - 70, 70, h - 10],
                [w - 70, 10, w - 10, 70],
                [10, 10, 70, 70],
            )
            if not any(
                (
                    c[0] < bx[2] and bx[0] < c[2] and (c[1] < bx[3]) and (bx[1] < c[3])
                    for bx in taken
                )
            )
        )
    )
    extra_id = max((b["block_id"] for b in m["blocks"])) + 1
    m["blocks"].append(
        {
            "block_id": extra_id,
            "box": spot,
            "label": art["label"],
            "score": 0.5,
            "order": None,
            "content": None,
            "kind": "none",
        }
    )
    res = contour.compare_pages(T, M)
    got = res["pairs"][i]
    by_truth = {e["truth"]: e for e in got["pairs"]}
    lost = by_truth[page_mod.anchor(i, art["block_id"])]
    assert lost["verdict"] == "missed" and lost["by"] == "A" and (lost["run"] is None)
    assert lost["why"] and lost["fate"] == "not_seen"
    assert f"{lost['why']} ({art['label']})" in res["troubles"]
    renamed = by_truth[page_mod.anchor(i, txt["block_id"])]
    assert renamed["verdict"] == "matched" and renamed["label_ok"] is False
    assert renamed["run"] in res["per"]["label_errors"]
    extra = [e for e in got["extras"] if e["run"] == page_mod.anchor(i, extra_id)]
    assert extra == [
        {"run": page_mod.anchor(i, extra_id), "verdict": "spurious_box", "taken_for": None}
    ]
    assert res["troubles"]["spurious_box"] == 1, "the list and the count disagree"
    _each_model_box_once(got, m)
    assert res["totals"]["found"] == sum(
        (
            1
            for p in res["pairs"].values()
            for e in p["pairs"]
            if e["by"] == "A" and e["verdict"] == "matched"
        )
    )


def _each_model_box_once(got, m):
    a_finds = [e["run"] for e in got["pairs"] if e["by"] == "A" and e["run"]]
    b_finds = [
        e["b_run"]
        for e in got["pairs"]
        if e["b_run"]
        and policy.UNION.role(
            next(
                (
                    x["label"]
                    for x in m["blocks"]
                    if page_mod.anchor(m["index"], x["block_id"]) == e["b_run"]
                )
            )
        )
        != "artifact"
    ]
    extras = [e["run"] for e in got["extras"]]
    assert len(set(a_finds)) == len(a_finds) and len(set(b_finds)) == len(b_finds)
    assert len(set(extras)) == len(extras)
    assert not set(a_finds) & set(extras) and (not set(a_finds) & set(b_finds))
    assert not set(b_finds) & set(extras)
    assert sorted(a_finds + b_finds + extras) == sorted(_anchors(m["index"], m["blocks"]))


def _one_page(slovar, want_artefact=True):
    T = truth_pages(slovar.truth_dir)
    i, t = next(
        (
            (i, t)
            for i, t in T.items()
            if any((policy.UNION.role(b["label"]) == "artifact" for b in t["blocks"]))
        )
    )
    return (i, t, _model_of({i: t})[i])


def test_a_box_pass_b_took_for_an_artefact_pass_a_missed_is_in_the_list_once(slovar):
    i, t, m = _one_page(slovar)
    art = next((b for b in t["blocks"] if policy.UNION.role(b["label"]) == "artifact"))
    text_label = next((lb for lb in policy.UNION.labels if policy.UNION.role(lb) == "text"))
    for b in m["blocks"]:
        if b["block_id"] == art["block_id"]:
            b["label"] = text_label
    res = contour.compare_pages({i: t}, {i: m})
    got = res["pairs"][i]
    e = next((e for e in got["pairs"] if e["truth"] == page_mod.anchor(i, art["block_id"])))
    eater = page_mod.anchor(i, art["block_id"])
    assert e["verdict"] == "missed" and e["by"] == "A" and (e["run"] is None)
    assert e["b_run"] == eater and e["b_label_ok"] is False
    assert e["fate"] == "called_text"
    assert eater in res["per"]["label_errors"], "the label metric counted the pair"
    assert not any((x["run"] == eater for x in got["extras"]))
    _each_model_box_once(got, m)


def test_an_artefact_box_pass_a_left_and_pass_b_took_is_one_extra_that_says_so(slovar):
    i, t, m = _one_page(slovar)
    txt = next((b for b in t["blocks"] if policy.UNION.role(b["label"]) == "text"))
    arte_label = next(
        (b["label"] for b in t["blocks"] if policy.UNION.role(b["label"]) == "artifact")
    )
    for b in m["blocks"]:
        if b["block_id"] == txt["block_id"]:
            b["label"] = arte_label
    res = contour.compare_pages({i: t}, {i: m})
    got = res["pairs"][i]
    box = page_mod.anchor(i, txt["block_id"])
    e = next((e for e in got["pairs"] if e["truth"] == box))
    assert e["verdict"] == "matched" and e["by"] == "B" and (e["run"] == box)
    assert e["label_ok"] is False and e["b_run"] == box
    ex = [x for x in got["extras"] if x["run"] == box]
    assert ex == [{"run": box, "verdict": "spurious_box", "taken_for": box}]
    assert res["troubles"]["spurious_box"] == 1
    _each_model_box_once(got, m)


def test_label_ok_is_the_drawn_pairs_and_the_label_metrics_pair_rides_beside(slovar):
    i, t, m = _one_page(slovar)
    art = next((b for b in t["blocks"] if policy.UNION.role(b["label"]) == "artifact"))
    text_label = next((lb for lb in policy.UNION.labels if policy.UNION.role(lb) == "text"))
    x0, y0, x1, y1 = art["box"]
    loose_id = max((b["block_id"] for b in m["blocks"])) + 1
    for b in m["blocks"]:
        if b["block_id"] == art["block_id"]:
            b["label"] = text_label
    m["blocks"].append(
        {
            "block_id": loose_id,
            "box": [x0 - 6, y0 - 6, x1 + 6, y1 + 6],
            "label": art["label"],
            "score": 0.9,
            "order": None,
            "content": None,
            "kind": "none",
        }
    )
    res = contour.compare_pages({i: t}, {i: m})
    got = res["pairs"][i]
    e = next((e for e in got["pairs"] if e["truth"] == page_mod.anchor(i, art["block_id"])))
    loose, exact = (page_mod.anchor(i, loose_id), page_mod.anchor(i, art["block_id"]))
    assert e["verdict"] == "matched" and e["by"] == "A"
    assert e["run"] == loose and e["label_ok"] is True
    assert e["b_run"] == exact and e["b_label_ok"] is False
    assert exact in res["per"]["label_errors"] and loose not in res["per"]["label_errors"]
    _each_model_box_once(got, m)


def test_two_rasters_refuse_in_page_pairs_as_in_compare(slovar):
    i, t, m = _one_page(slovar)
    m = dict(m, width=t["width"] * 2, height=t["height"] * 2)
    with pytest.raises(contour.MetricError, match="DIFFERENT rasters"):
        contour.page_pairs(t, m)


def test_a_page_that_says_it_is_not_labelled_is_left_out_and_said(slovar):
    T = truth_pages(slovar.truth_dir)
    M = _model_of(T)
    T[0]["meta"]["labelled"] = False
    T[1]["meta"]["labelled"] = True
    res = contour.compare_pages(T, M)
    assert res["labelled"] == {"yes": 1, "no": 1, "not_said": len(T) - 2}
    assert list(res["pairs"]) == [1], "a page that did not say was compared"
    assert res["text_and_furniture"]["pages_total"] == 1
    assert res["jumps"]["page_count"] == 1, "the jumps describe pages the rest left out"
    assert res["sense"]["objects"] == sum(
        (1 for b in T[1]["blocks"] if policy.UNION.role(b["label"]) == "artifact")
    )
    from metrics import bench as bench_mod

    said = bench_mod.labelled_said(bench_mod.labelled_of(T))
    assert said and (not bench_mod.labelled_said(bench_mod.labelled_of(_model_of(T))))
    assert contour.page_pairs(T[0], M[0], said=said) is None
    assert contour.page_pairs(T[1], M[1], said=said) == res["pairs"][1]
    assert contour.page_pairs(T[2], M[2], said=said) is None
    assert contour.page_pairs(T[2], M[2]) is not None, "a silent truth compares whole"
    with support.said() as said:
        contour.report(res)
    assert any(("yes 1, no 1" in ln and "only the pages that say yes" in ln for ln in said))
    for t in T.values():
        t["meta"]["labelled"] = False
    with pytest.raises(contour.MetricError, match="not a zero"):
        contour.compare_pages(T, M)
