"""The second level: blocks read by a model -- the whole path, for no cents.

Our half is checked, from prompt routes to the snapshot, five kinds of zero
among them. The model is stood in for by `fake_vlm.FakeVlm`, an
OpenAI-compatible endpoint answering to order; it does not read the picture
and does not pretend to.

The order of work is bench and instrument first, model after, so a trap that
is ours is found before a card is rented.
"""
import json
import os

import pytest
from booksmith.core.errors import Refusal

import support
from fake_vlm import FakeVlm

from booksmith.core import otsl
from booksmith.core.page import Block, Page
from booksmith.processing.read import Ask, Route
from booksmith.processing.read.transports import openai_http as vhttp
from booksmith.processing.read import driver as vrun
from booksmith.processing.read.readers.paddleocr_vl import PaddleOcrVl
from booksmith.core import policy

_V2 = policy.POLICIES["PP-DocLayoutV2"]


# -------------------------------------------------------------- routes ---

def test_every_label_of_every_dictionary_has_a_route():
    """A label without a route drops the run before the first cent. No default
    "whatever I don't know, ask OCR:": each detector has its own dictionary, and
    an unknown class would otherwise leave under the wrong prompt."""
    from booksmith.core import policy
    for d in policy.POLICIES.values():
        PaddleOcrVl(d).cover(d.labels)             # throws on a hole


def test_unknown_label_is_loud():
    r = PaddleOcrVl(_V2)
    try:
        r.cover(["table", "no_such_thing"])
    except ValueError as e:
        assert "no_such_thing" in str(e)
    else:
        raise AssertionError("a label with no route passed in silence")


def test_kind_comes_from_the_prompt_not_from_the_answer():
    """The PROMPT declares the kind: ask for a table, get kind `otsl`."""
    r = PaddleOcrVl(_V2).routes()
    assert r["table"].kind == "otsl" and r["table"].prompt == "Table Recognition:"
    assert r["display_formula"].kind == "latex"
    assert r["text"].kind == "text" and r["text"].prompt == "OCR:"


def test_silence_carries_a_reason():
    """"Not asked" is a reason, not a forgotten label."""
    r = PaddleOcrVl(_V2).routes()
    for lab in ("image", "header_image", "footer_image"):
        assert not r[lab].asked()
        assert r[lab].why, f"{lab} is silent with no reason given"


def test_route_with_unknown_kind_is_loud():
    try:
        Route("OCR:", "markdown").check("text")
    except ValueError as e:
        assert "is not declared" in str(e)
    else:
        raise AssertionError("a kind outside KINDS passed in silence")


def test_declared_kinds_agree_with_the_book():
    """The reader's kinds are names `books apply` accepts."""
    from booksmith.core.page import KINDS
    for name in ("PP-DocLayoutV2", "Docling", "DocLayNet"):
        for rt in PaddleOcrVl(policy.POLICIES[name]).routes().values():
            if rt.asked():
                assert rt.kind in KINDS, f"the book does not know the kind {rt.kind}"


# ----------------------------------------------------------- transport ---

def _t(url, model="PaddleOCR-VL-1.6-0.9B"):
    os.environ["VLM_ENDPOINT"] = url
    os.environ["MODEL_NAME"] = model
    return vhttp.Http()


def test_transport_asks_who_is_answering():
    """The check asks not "are you alive" but "what is your name": an orphan of
    a previous run holding the video memory answers /v1/models too."""
    with FakeVlm({"text": "ok"}) as s:
        out = _t(s.url).check()
        assert out["matched"] and out["models_on_server"] == [s.model]


def test_wrong_model_name_stops_the_run():
    from booksmith.core.errors import Refusal
    with FakeVlm({"text": "ok"}, model="a-completely-different-one") as s:
        with pytest.raises(Refusal, match="a-completely-different-one"):
            _t(s.url).check()


def test_delivery_refusal_is_a_value_not_a_throw():
    """A refused delivery comes back as a value: a run over five hundred
    blocks must not die of one broken connection."""
    png = _png()
    with FakeVlm({"http": 500}) as s:
        _t(s.url)
        os.environ["VLM_RETRIES"] = "0"
        said = vhttp.Http().send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert said.error and said.text is None
        assert not said.answered()
    os.environ.pop("VLM_RETRIES", None)


def test_answer_200_is_never_repeated():
    """Asking again after an answer is forbidden by rule and said in code: a 200
    with nothing in it is an answer, and asking again would be repairing the
    model. Calls to the service are counted: exactly one."""
    png = _png()
    os.environ["VLM_RETRIES"] = "3"
    with FakeVlm({"text": ""}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 1, f"one answer took {len(s.seen)} calls"
    os.environ.pop("VLM_RETRIES", None)


def test_delivery_refusal_is_repeated():
    """A refused delivery is repeated: there was no answer at all."""
    png = _png()
    os.environ["VLM_RETRIES"] = "2"
    with FakeVlm({"http": 503}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 3, f"calls {len(s.seen)}, expected 3"
    os.environ.pop("VLM_RETRIES", None)


def test_empty_crop_is_loud():
    """An empty crop never leaves for the model: on a blank white sheet this
    model returns full tables, and emptiness sent would come back as an
    invention written down as reading."""
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "empty.png")
    open(p, "wb").close()
    try:
        vhttp._data_uri(p)
    except ValueError as e:
        assert "the crop is empty" in str(e)
    else:
        raise AssertionError("an empty crop would have gone to the model")


def test_the_very_crop_reaches_the_model():
    """That crop reached the model, not the neighbouring one: the bytes that
    arrived and the prompt beside them are both compared."""
    png = _png()
    n = os.path.getsize(png)
    with FakeVlm({"text": "ok"}) as s:
        _t(s.url).send(Ask("p0-b0", png, "Table Recognition:", "otsl", "table"))
        assert s.seen[0]["bytes"] == n
        assert s.seen[0]["prompt"] == "Table Recognition:"


# ------------------------------------------------------------- parsing ---

def test_otsl_grid_matches_html_grid_cell_for_cell():
    """A grid from OTSL and the same grid from HTML agree address by address:
    the instrument must read both, or a faultless OTSL answer scores zero."""
    # Not the OTSL parser alone but the function the instrument pulls a grid
    # out of a model answer with.
    from booksmith.datasets.metrics import text as booktext
    want = {(0, 0): "A", (0, 1): "B", (1, 0): "1", (1, 1): "2"}
    g1 = booktext._answer_grid("<fcel>A<fcel>B<nl><fcel>1<fcel>2<nl>", "otsl")
    g2 = booktext._answer_grid("<table><tr><td>A</td><td>B</td></tr>"
                               "<tr><td>1</td><td>2</td></tr></table>", "html")
    # The declared kind does not lock the parser: HTML for a table is read.
    g3 = booktext._answer_grid("<fcel>A<fcel>B<nl><fcel>1<fcel>2<nl>", "html")
    assert g1 == g2 == g3 == want


def test_otsl_span_occupies_all_its_addresses():
    """A spanning cell occupies every address, as colspan does in HTML."""
    g = otsl.grid("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[(0, 0)] == g[(0, 1)] == "head"


def test_torn_otsl_is_counted_not_repaired():
    """Torn OTSL stays torn and is counted as a number: padding it, as the
    vendor does, returns a table torn at the ceiling as a plausible one."""
    _, t = otsl.parse("<fcel>a<fcel>b<nl><fcel>c<nl>")
    assert t["rows_of_unequal_length"] == 1
    _, t2 = otsl.parse("<lcel>x<nl>")
    assert t2["continuations_to_nowhere"] == 1


def test_not_otsl_is_none_not_empty():
    """"Not OTSL" and "the table is empty" are different answers."""
    assert otsl.grid("<table><tr><td>x</td></tr></table>") is None
    assert otsl.grid("just prose") is None
    assert otsl.grid("") is None


def test_sniffed_kind_never_overrides_the_declared_one():
    """A guess at the kind lies BESIDE and decides nothing."""
    assert vrun._sniff("<fcel>a<nl>") == "otsl"
    assert vrun._sniff("prose") == "text"
    assert vrun._sniff("") == "empty"


# ------------------------------------------------------- the book pass ---

def _png():
    """A real small picture: the transport reads bytes, not a path."""
    import tempfile
    import pymupdf
    d = os.path.join(tempfile.mkdtemp(), "c.png")
    doc = pymupdf.open()
    pg = doc.new_page(width=60, height=30)
    pg.insert_text((5, 20), "abc")
    pg.get_pixmap(dpi=72).save(d)
    doc.close()
    return d


def _book(tmp):
    """A tiny book and its detect directory: text, table and a picture."""
    import pymupdf
    from booksmith.core import stamp
    pdf = os.path.join(tmp, "c.pdf")
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pg.insert_text((20, 40), "a line of prose")
    pg.insert_text((20, 120), "table")
    doc.save(pdf, garbage=3, deflate=True)
    doc.close()

    os.makedirs(os.path.join(tmp, "detect", "pages"), exist_ok=True)
    page = Page(index=0, width=400, height=400, dpi=144.0, blocks=[
        Block(block_id=0, box=(30, 40, 300, 100), label="text", score=0.9,
              order=1),
        Block(block_id=1, box=(30, 200, 300, 300), label="table", score=0.8,
              order=2),
        Block(block_id=2, box=(30, 320, 300, 380), label="image", score=0.7,
              order=3),
    ])
    with open(os.path.join(tmp, "detect", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        json.dump(page.to_json(), f, ensure_ascii=False)
    with open(os.path.join(tmp, "detect", "run.json"), "w",
              encoding="utf-8") as f:
        json.dump({"source": {"path": pdf, "sha256": stamp.sha256(pdf)},
                   "raster": {"dpi": 144.0}, "identity": "a fake detection",
                   "commit": None, "adapter": {"name": "a fake one"},
                   "weights": {"layout": None}}, f, ensure_ascii=False)
    return pdf


def _run(tmp, plan, out_dir=None, snapshot=False, **kw):
    out = out_dir or os.path.join(tmp, "read")
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        os.environ["MODEL_NAME"] = s.model
        r = PaddleOcrVl(_V2)
        t = vrun.read_book(os.path.join(tmp, "detect"), out, r, vhttp.Http(),
                           **kw)
        if snapshot:
            # The guard reads `run.json`, which only `snapshot()` writes: a run
            # without one is not a run and nothing is refused over it.
            vrun.snapshot(os.path.join(tmp, "detect"), out, r, vhttp.Http(),
                          t, {})
    return out, t


def test_read_fills_content_in_the_same_page_schema():
    """Reading produces the same `pages/*.json` detection does."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "a line of prose"},
                        "Table Recognition:": {"text": "<fcel>A<fcel>B<nl>"}})
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    by = {b.block_id: b for b in p.blocks}
    assert by[0].content == "a line of prose" and by[0].kind == "text"
    assert by[1].content == "<fcel>A<fcel>B<nl>" and by[1].kind == "otsl"
    # The picture was never asked, and that is not model silence.
    assert by[2].content is None and by[2].kind == "none"
    assert t["not_asked"] == 1 and t["read"] == 2


def test_five_zeroes_are_counted_apart():
    """Not asked / delivery refused / stayed silent / truncated / read."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": ""},                       # silence
                        "Table Recognition:": {"text": "<fcel>x<nl>",
                                               "finish": "length"}})
    assert t["not_asked"] == 1, t
    assert t["model_silent"] == 1, t
    assert t["hit_ceiling"] == 1, t
    assert t["read"] == 1, t
    assert t["delivery_failed"] == 0, t


def test_delivery_refusal_does_not_look_like_silence():
    """A refused connection is not model silence: different troubles."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    os.environ["VLM_RETRIES"] = "0"
    out, t = _run(tmp, {"http": 500})
    assert t["delivery_failed"] == 2 and t["model_silent"] == 0, t
    os.environ.pop("VLM_RETRIES", None)


def test_model_bytes_are_untouched():
    """Model bytes reach the page byte for byte, rubbish included."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    dirt = "  <b>not closed &amp;\n\twhitespace  "
    out, _ = _run(tmp, {"OCR:": {"text": dirt},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    assert p.blocks[0].content == dirt


def test_observed_lives_beside_not_inside():
    """Seconds, tokens, the kind guess -- in answers/, not in the text."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, _ = _run(tmp, {"OCR:": {"text": "prose"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with open(os.path.join(out, "answers", "p0000.json"), encoding="utf-8") as f:
        a = {x["anchor"]: x for x in json.load(f)["answers"]}
    assert a["p0000-b0"]["observed"]["kind_sniffed"] == "text"
    assert a["p0000-b1"]["observed"]["kind_sniffed"] == "otsl"
    assert "seconds" in a["p0000-b0"]
    # And not one mark of ours in the text itself.
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    assert p.blocks[0].content == "prose"


def test_swapped_pdf_stops_the_run():
    """A book swapped after detection drops the reading, aloud."""
    import tempfile
    tmp = tempfile.mkdtemp()
    pdf = _book(tmp)
    with open(pdf, "ab") as f:
        f.write(b"% extra byte\n")   # no non-ASCII byte goes in a b"" literal
    try:
        _run(tmp, {"OCR:": {"text": "x"}})
    except Refusal as e:
        assert "sha256" in str(e)
    else:
        raise AssertionError("the reading went on against a swapped book")


def test_resume_does_not_ask_twice():
    """Resuming does not pay twice for a block already read."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    plan = {"OCR:": {"text": "prose"},
            "Table Recognition:": {"text": "<fcel>a<nl>"}}
    out, t1 = _run(tmp, plan)
    assert t1["reused_from_previous_run"] == 0
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        t2 = vrun.read_book(os.path.join(tmp, "detect"), out,
                            PaddleOcrVl(_V2), vhttp.Http(),
                            resume=True)
        assert len(s.seen) == 0, f"{len(s.seen)} blocks were asked again"
    assert t2["reused_from_previous_run"] == 2


def test_empty_run_is_not_a_success():
    """Zero blocks asked is not a success but an empty run."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    try:
        _run(tmp, {"OCR:": {"text": "x"}}, pages_want={999})
    except Refusal as e:
        assert "empty" in str(e)
    else:
        raise AssertionError("an empty page set passed in silence")


def test_snapshot_carries_prompts_and_our_parser():
    """The snapshot carries prompts, generation and the hash of our OTSL parser:
    prompts are the only thing here that steers the answer, and the parser
    decides the numbers no less than the model does."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "prose"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with FakeVlm({"text": "x"}) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        p = vrun.snapshot(os.path.join(tmp, "detect"), out,
                          PaddleOcrVl(_V2), vhttp.Http(), t,
                          {"detect": "detect", "out": out})
    with open(p, encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["prompts"]["table"] == "Table Recognition:"
    assert snap["generation"]["max_tokens"] == 4096
    assert len(snap["adapter"]["sha256_otsl_parser"]) == 64
    assert snap["fingerprint"]["weights"]["dir"] is None
    # The key does not go into the snapshot: snapshots are committed to git.
    assert snap["transport_fingerprint"]["api_key"] == "no"


# ------------------------------------------------------------- preview ---
# `books crop`: the check is not "it wrote something" but the same bytes the
# paid path sends.


def _preview(tmp):
    out = os.path.join(tmp, "crop")
    r = PaddleOcrVl(_V2)
    t = vrun.read_book(os.path.join(tmp, "detect"), out, r, None,
                       resume=False, preview=True)
    return out, t


def test_the_preview_cuts_the_very_crops_the_paid_run_cuts():
    """Byte for byte, and the questions with them: a preview whose pictures
    differ from the paid run's is worse than none, being looked at before the
    money and believed."""
    import hashlib
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    prev, tp = _preview(tmp)
    paid, _ = _run(tmp, {"OCR:": {"text": "prose"},
                         "Table Recognition:": {"text": "<fcel>a<nl>"}})

    def crops(d):
        c = os.path.join(d, "crops")
        return {f: hashlib.sha256(open(os.path.join(c, f), "rb").read()
                                  ).hexdigest() for f in os.listdir(c)}
    a, b = crops(prev), crops(paid)
    # The names match by construction, so the message must name what differs.
    diff = sorted(set(a.items()) ^ set(b.items()))
    assert a and not diff, (
        f"the preview cut something else: {[(n, h[:12]) for n, h in diff]} "
        f"(preview {len(a)} crops, paid {len(b)})")

    asks = json.load(open(os.path.join(prev, "would_ask.json"),
                          encoding="utf-8"))["asks"]
    assert {x["anchor"] for x in asks} == {f[:-4] for f in a}
    assert tp["would_ask"] == len(asks) == 2, tp
    # The prompt and the kind decide what comes back; a crop alone shows half.
    assert {x["kind"] for x in asks} == {"text", "otsl"}
    assert all(x["prompt"] for x in asks)
    # The resolution rule with the reason it fired: too coarse a crop is
    # decided here, not after the run.
    assert all(x["crop_dpi"] > 0 and x["crop_dpi_reason"] for x in asks)


def test_the_preview_writes_nothing_a_paid_run_would_believe():
    """No `read_with.json`, no `pages/`, no `answers/`: a preview has no
    transport, so `read_with.json` would name a setup no money bought, and an
    empty `pages/` reads as a reading that returned nothing."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    prev, t = _preview(tmp)
    left = sorted(os.listdir(prev))
    assert left == ["crops", "would_ask.json"], left
    assert t.get("preview") is True and "read" not in t.get("by_kind", {})


def _raster_book(tmp):
    """A book whose crop is downscaled to the model's ceiling: a 2000x2000
    raster on 200x200 pt with the box nearly the whole sheet, so the rule
    answers with a fraction. The plain fixture cannot separate the two dpi."""
    import pymupdf
    from booksmith.core import stamp
    pdf = os.path.join(tmp, "r.pdf")
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2000, 2000), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    for i in range(0, 2000, 40):          # ink, so the crop is not blank
        pix.set_rect(pymupdf.IRect(0, i, 2000, i + 6), (10, 10, 10))
    pg.insert_image(pg.rect, pixmap=pix)
    doc.save(pdf, garbage=3, deflate=True)
    doc.close()

    os.makedirs(os.path.join(tmp, "detect", "pages"), exist_ok=True)
    page = Page(index=0, width=400, height=400, dpi=144.0, blocks=[
        Block(block_id=0, box=(10, 10, 390, 390), label="text", score=0.9,
              order=1)])
    with open(os.path.join(tmp, "detect", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        json.dump(page.to_json(), f, ensure_ascii=False)
    with open(os.path.join(tmp, "detect", "run.json"), "w",
              encoding="utf-8") as f:
        json.dump({"source": {"path": pdf, "sha256": stamp.sha256(pdf)},
                   "raster": {"dpi": 144.0}, "identity": "a fake detection",
                   "commit": None, "adapter": {"name": "a fake one"},
                   "weights": {"layout": None}}, f, ensure_ascii=False)
    return pdf


def test_the_preview_reports_the_dpi_it_cut_at_not_the_rule_s_number():
    """The same key must mean the same thing in both files: `crop_dpi` is the
    deed and `crop_dpi_by_rule` the rule, and `crop.cut` renders at `int(dpi)`
    while the rule gives a fraction."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _raster_book(tmp)
    prev, _ = _preview(tmp)
    ask = json.load(open(os.path.join(prev, "would_ask.json"),
                         encoding="utf-8"))["asks"][0]
    assert ask["crop_dpi_reason"] == "downscaled_to_model_max", ask
    assert ask["crop_dpi"] != ask["crop_dpi_by_rule"], (
        f"the fixture no longer separates the two quantities: {ask}")

    paid, _ = _run(tmp, {"OCR:": {"text": "prose"}})
    obs = json.load(open(os.path.join(paid, "answers", "p0000.json"),
                         encoding="utf-8"))["answers"][0]["observed"]
    assert ask["crop_dpi"] == obs["crop_dpi"], (
        f"preview says it cut at {ask['crop_dpi']}, the paid run recorded "
        f"{obs['crop_dpi']}")
    assert ask["crop_dpi_by_rule"] == obs["crop_dpi_by_rule"]
    assert ask["crop_dpi_reason"] == obs["crop_dpi_reason"]


def test_a_preview_refuses_to_land_on_a_paid_read_directory():
    """The crops are something a paid run believes: `answers/*.json` describes
    those very files, the only surviving picture of what the money bought, and
    a preview writes `crops/<anchor>.png` under the same names."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    paid, _ = _run(tmp, {"OCR:": {"text": "prose"},
                         "Table Recognition:": {"text": "<fcel>a<nl>"}})
    was = {f: open(os.path.join(paid, "crops", f), "rb").read()
           for f in os.listdir(os.path.join(paid, "crops"))}
    r = PaddleOcrVl(_V2)
    try:
        vrun.read_book(os.path.join(tmp, "detect"), paid, r, None,
                       resume=False, preview=True)
    except Refusal as e:
        assert "answers" in str(e), e
    else:
        raise AssertionError("the preview landed on a paid read directory")
    now = {f: open(os.path.join(paid, "crops", f), "rb").read()
           for f in os.listdir(os.path.join(paid, "crops"))}
    assert now == was, "the paid crops were touched before the refusal"


def test_the_preview_names_the_blocks_it_would_not_ask_about():
    """The preview files a record for every block, not only the questions: what
    a run would skip and why is half the answer to "what will this run do
    before I pay"."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)                      # its third block is a picture: not asked
    prev, _ = _preview(tmp)
    d = json.load(open(os.path.join(prev, "would_ask.json"), encoding="utf-8"))
    assert [x["anchor"] for x in d["not_asked"]] == ["p0000-b2"], d["not_asked"]
    assert d["not_asked"][0]["not_asked"], "the reason is missing"
    assert d["crop_failed"] == []


def test_a_preview_may_not_resume():
    """A preview may not resume: `resume` would show every block as "would ask"
    on a book already half read, and the answers it would reuse live in the
    read directory, where a preview may not write."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    r = PaddleOcrVl(_V2)
    try:
        vrun.read_book(os.path.join(tmp, "detect"),
                       os.path.join(tmp, "crop2"), r, None,
                       resume=True, preview=True)
    except Refusal as e:
        assert "resume" in str(e)
    else:
        raise AssertionError("a resuming preview passed in silence")


def test_a_second_reading_at_other_settings_may_not_resume_the_first():
    """A run at another temperature, seed or prompt may not resume the first:
    the identity the guard asks is the same number the snapshot records, so
    what refuses a run and what is written into it cannot be two."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, _ = _run(tmp, {"OCR:": {"text": "prose"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}},
                  snapshot=True)
    snap = json.load(open(os.path.join(out, "run.json"), encoding="utf-8"))
    assert snap["identity"], "the read snapshot records no identity"

    with support.env(VLM_TEMPERATURE="0.7"):
        try:
            _run(tmp, {"OCR:": {"text": "prose"}}, out_dir=out)
        except Refusal as e:
            assert "DIFFERENT experiment" in str(e), e
            assert "--run" in str(e)
        else:
            raise AssertionError(
                "a reading at another temperature resumed the first one")
    # The same settings again is a resume, and that is allowed.
    _run(tmp, {"OCR:": {"text": "prose"},
               "Table Recognition:": {"text": "<fcel>a<nl>"}}, out_dir=out)
