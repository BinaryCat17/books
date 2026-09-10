"""The reading instrument: the last line of the report, and its zeros"""

from metrics import text
import support


def _pages(blocks, side=None):
    return {
        0: {
            "index": 0,
            "width": 100,
            "height": 100,
            "dpi": 144.0,
            "blocks": blocks,
            "meta": {"artifact_truth": side} if side else {},
        }
    }


def _text_block(i, content):
    return {
        "block_id": i,
        "box": [0, i * 10, 90, i * 10 + 8],
        "label": "text",
        "content": content,
        "kind": "text" if content else "none",
    }


def _formula_block(i, content):
    return {
        "block_id": i,
        "box": [0, i * 10, 90, i * 10 + 8],
        "label": "display_formula",
        "content": content,
        "kind": "latex" if content else "none",
    }


def _say(truth, answer):
    with support.said() as out:
        text.report(text.measure_pages(truth, answer))
    return "\n".join(out)


def test_silence_is_not_reported_as_perfect_reading():
    T = _pages([_text_block(0, "first"), _text_block(1, "second")])
    P = _pages([_text_block(0, None), _text_block(1, None)])
    s = _say(T, P)
    assert "there was NOTHING to compare" in s
    assert "no text blocks with an error" not in s


def test_perfect_reading_counts_only_text_in_the_text_line():
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)], side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, "x = 1")])
    s = _say(T, P)
    assert "no text blocks with an error: CER 0 on all 1 computed of 1" in s
    assert "no artifact blocks with an error: CER 0 on all 1 computed of 1" in s


def test_one_wrong_letter_in_a_formula_does_not_crash():
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)], side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, "z = 1")])
    s = _say(T, P)
    assert "worst artifact block" in s
    assert "WER" not in s.split("worst artifact block")[1].split("\n")[0]


def test_silent_formulas_are_not_a_measured_one():
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)], side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, None)])
    s = _say(T, P)
    assert "THERE IS NO ANSWER TO A SINGLE ONE" in s
    assert "CER 1.0000" not in s


def test_artefact_with_truth_is_not_a_bait():
    T = _pages([_formula_block(0, None)], side={"0": {"text": "x = 1"}})
    P = _pages([_formula_block(0, "x = 1")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["block_count"] == 1
    assert r["artifacts_with_truth"]["CER"] == 0.0
    assert r["baits"]["artifacts"] == 0


def test_artefact_without_truth_stays_a_bait():
    T = _pages(
        [{"block_id": 0, "box": [0, 0, 90, 8], "label": "image", "content": None, "kind": "none"}]
    )
    P = _pages(
        [
            {
                "block_id": 0,
                "box": [0, 0, 90, 8],
                "label": "image",
                "content": "made up",
                "kind": "text",
            }
        ]
    )
    r = text.measure_pages(T, P)
    assert r["baits"]["artifacts"] == 1 and r["baits"]["read"] == 1
    assert r["artifacts_with_truth"]["block_count"] == 0


def test_invention_on_declared_emptiness_is_counted():
    T = _pages([_formula_block(0, None)], side={"0": {"text": ""}})
    P = _pages([_formula_block(0, "made up fourteen")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["invented_on_empty_truth"] == 1


def test_two_truths_on_one_artefact_are_loud():
    T = _pages([_formula_block(0, None)], side={"0": {"text": "x = 1", "table": [["a", "b"]]}})
    P = _pages([_formula_block(0, "x = 1")])
    try:
        text.measure_pages(T, P)
    except text.TextError as e:
        assert "BOTH a table grid" in str(e) or "grid" in str(e)
    else:
        raise AssertionError("two truths on one block passed in silence")


def test_table_in_otsl_scores_like_the_same_table_in_html():
    grid = [["A", "B"], ["1", "2"]]
    T = _pages(
        [{"block_id": 0, "box": [0, 0, 90, 8], "label": "table", "content": None, "kind": "none"}],
        side={"0": {"table": grid}},
    )
    as_html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
    as_otsl = "<fcel>A<fcel>B<nl><fcel>1<fcel>2<nl>"
    got = []
    for body, kind in ((as_html, "html"), (as_otsl, "otsl")):
        P = _pages(
            [{"block_id": 0, "box": [0, 0, 90, 8], "label": "table", "content": body, "kind": kind}]
        )
        b = text.measure_pages(T, P)["tables"]
        got.append((b["cells_matched"], b["given_as_text"], b["cer_cells"]))
    assert got[0] == got[1] == (4, 0, 0.0), got


def test_a_cell_with_angle_brackets_survives_the_round_trip():
    was = {(0, 0): "a<b & c", (0, 1): "plain", (1, 0): '"quoted"', (1, 1): "5 > 3"}
    now = text._html_grid(text._grid_html(was))
    assert now == was, (
        f"the grid round trip lost content:\n  was  {was}\n  now  {now}\nA cell must be escaped -- otherwise the battery measures a different string than the one it reports on"
    )
