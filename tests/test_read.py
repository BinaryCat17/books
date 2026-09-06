"""The second level: blocks read by a model -- the whole path, for no cents.

OUR half is checked, from prompt routes to the snapshot, five different
zeroes among them. The model is stood in for by `fake_vlm.FakeVlm`, an
OpenAI-compatible endpoint answering to order; it does not read the picture
and does not pretend to.

WHY BEFORE THE FIRST PAID RUN. The order of work here is the reverse of the
usual: bench and instrument first, model after. The previous second level was
debugged on a rented card -- thirteen launches, $0.52, two of them useful --
and every trap turned out to be ours, not one the model's.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fake_vlm import FakeVlm                                # noqa: E402

from booksmith import otsl                                  # noqa: E402
from booksmith.models.base import Block, Page               # noqa: E402
from booksmith.read import Ask, Route                       # noqa: E402
from booksmith.read import http as vhttp                    # noqa: E402
from booksmith.read import run as vrun                      # noqa: E402
from booksmith.models.paddleocr_vl.reader import PaddleOcrVl  # noqa: E402


# -------------------------------------------------------------- routes ---

def test_every_label_of_every_dictionary_has_a_route():
    """A label without a route drops the run BEFORE the first cent.

    No default "whatever I don't know, ask OCR:", deliberately: each detector
    has its OWN label dictionary, and the twenty-sixth class of new weights
    would leave under the wrong prompt, its answer written down as reading.
    """
    from booksmith import policy
    for name, d in policy.POLICIES.items():
        PaddleOcrVl(name).cover(d.keys())          # throws on a hole


def test_unknown_label_is_loud():
    r = PaddleOcrVl("PP-DocLayoutV2")
    try:
        r.cover(["table", "чего-такого-нет"])
    except ValueError as e:
        assert "чего-такого-нет" in str(e)
    else:
        raise AssertionError("ярлык без маршрута прошёл молча")


def test_kind_comes_from_the_prompt_not_from_the_answer():
    """The PROMPT declares the kind: ask for a table, get kind `otsl`."""
    r = PaddleOcrVl("PP-DocLayoutV2").routes()
    assert r["table"].kind == "otsl" and r["table"].prompt == "Table Recognition:"
    assert r["display_formula"].kind == "latex"
    assert r["text"].kind == "text" and r["text"].prompt == "OCR:"


def test_silence_carries_a_reason():
    """"Not asked" is a reason, not a forgotten label."""
    r = PaddleOcrVl("PP-DocLayoutV2").routes()
    for lab in ("image", "header_image", "footer_image"):
        assert not r[lab].asked()
        assert r[lab].why, f"{lab} молчит без причины"


def test_route_with_unknown_kind_is_loud():
    try:
        Route("OCR:", "маркдаун").check("text")
    except ValueError as e:
        assert "не объявлен" in str(e)
    else:
        raise AssertionError("вид мимо KINDS прошёл молча")


def test_declared_kinds_agree_with_the_book():
    """The reader's kinds are names `books apply` accepts."""
    from booksmith.doc.apply import KINDS
    for name in ("PP-DocLayoutV2", "Docling", "DocLayNet"):
        for rt in PaddleOcrVl(name).routes().values():
            if rt.asked():
                assert rt.kind in KINDS, f"вид {rt.kind} книге неизвестен"


# ----------------------------------------------------------- transport ---

def _t(url, model="PaddleOCR-VL-1.6-0.9B"):
    os.environ["VLM_ENDPOINT"] = url
    os.environ["MODEL_NAME"] = model
    return vhttp.Http()


def test_transport_asks_who_is_answering():
    """The check asks not "are you alive" but "what is your name".

    Paid for on the first level: `curl /v1/models` was answered by an ORPHAN
    of the previous run holding 60 % of the video memory, and the script took
    it for its own.
    """
    with FakeVlm({"text": "ок"}) as s:
        out = _t(s.url).check()
        assert out["matched"] and out["models_on_server"] == [s.model]


def test_wrong_model_name_stops_the_run():
    with FakeVlm({"text": "ок"}, model="совсем-другая") as s:
        try:
            _t(s.url).check()
        except RuntimeError as e:
            assert "совсем-другая" in str(e)
        else:
            raise AssertionError("чужое имя модели прошло молча")


def test_delivery_refusal_is_a_value_not_a_throw(tmp_png=None):
    """A refused delivery comes back as a value: a run over five hundred
    blocks must not die of one broken connection."""
    png = _png()
    with FakeVlm({"http": 500}) as s:
        t = _t(s.url)
        os.environ["VLM_RETRIES"] = "0"
        said = vhttp.Http().send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert said.error and said.text is None
        assert not said.answered()
    os.environ.pop("VLM_RETRIES", None)


def test_answer_200_is_never_repeated():
    """Asking again after an answer is forbidden by rule and said in code.

    A 200 with nothing in it IS an answer, and asking again would be
    repairing the model. Calls to the service are counted: exactly one.
    """
    png = _png()
    os.environ["VLM_RETRIES"] = "3"
    with FakeVlm({"text": ""}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 1, f"на один ответ ушло {len(s.seen)} обращений"
    os.environ.pop("VLM_RETRIES", None)


def test_delivery_refusal_is_repeated():
    """A refused delivery is repeated: there was no answer at all."""
    png = _png()
    os.environ["VLM_RETRIES"] = "2"
    with FakeVlm({"http": 503}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 3, f"обращений {len(s.seen)}, ждали 3"
    os.environ.pop("VLM_RETRIES", None)


def test_empty_crop_is_loud():
    """An empty crop never leaves for the model.

    On a blank white sheet this model returns full tables -- five different
    ones in five tries. Send emptiness and you get an invention written down
    as reading.
    """
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "пусто.png")
    open(p, "wb").close()
    try:
        vhttp._data_uri(p)
    except ValueError as e:
        assert "пуста" in str(e)
    else:
        raise AssertionError("пустая вырезка уехала бы в модель")


def test_the_very_crop_reaches_the_model():
    """THAT crop reached the model, not the neighbouring one.

    Paid for on the first level: a loop variable overwrote the scale factor,
    and 36 pages of 36 were written down unparsed on a faultless answer.
    """
    png = _png()
    n = os.path.getsize(png)
    with FakeVlm({"text": "ок"}) as s:
        _t(s.url).send(Ask("p0-b0", png, "Table Recognition:", "otsl", "table"))
        assert s.seen[0]["bytes"] == n
        assert s.seen[0]["prompt"] == "Table Recognition:"


# ------------------------------------------------------------- parsing ---

def test_otsl_grid_matches_html_grid_cell_for_cell():
    """A grid from OTSL and the same grid from HTML agree address by address.

    The reading instrument parsed a table ONLY out of HTML, so a faultless
    answer from PaddleOCR-VL -- which returns OTSL -- got "matched by address
    0 (0 %)" and the brand "handed over as text": the model accused of a
    defect in our parser.
    """
    # What is compared is NOT the OTSL parser but THE function the instrument
    # pulls a grid out of a model answer with. The first edition called
    # `otsl.grid` and `_html_grid` separately, and the mutation "blind to OTSL
    # again" passed it by: a broken `_answer_grid` never touched the check.
    from booksmith import text as booktext
    want = {(0, 0): "А", (0, 1): "Б", (1, 0): "1", (1, 1): "2"}
    g1 = booktext._answer_grid("<fcel>А<fcel>Б<nl><fcel>1<fcel>2<nl>", "otsl")
    g2 = booktext._answer_grid("<table><tr><td>А</td><td>Б</td></tr>"
                               "<tr><td>1</td><td>2</td></tr></table>", "html")
    # And the kind declared by the prompt does not lock the parser: a model
    # asked for a table and answering HTML HAS READ THE TABLE.
    g3 = booktext._answer_grid("<fcel>А<fcel>Б<nl><fcel>1<fcel>2<nl>", "html")
    assert g1 == g2 == g3 == want


def test_otsl_span_occupies_all_its_addresses():
    """A spanning cell occupies every address, as colspan does in HTML."""
    g = otsl.grid("<ched>шапка<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[(0, 0)] == g[(0, 1)] == "шапка"


def test_torn_otsl_is_counted_not_repaired():
    """Torn OTSL stays torn and is counted as a number.

    The vendor's `otsl_pad_to_sqr_v2` does the opposite -- pads and truncates
    in silence -- and a table torn at the ceiling comes back plausible.
    """
    _, t = otsl.parse("<fcel>a<fcel>b<nl><fcel>c<nl>")
    assert t["rows_of_unequal_length"] == 1
    _, t2 = otsl.parse("<lcel>x<nl>")
    assert t2["continuations_to_nowhere"] == 1


def test_not_otsl_is_none_not_empty():
    """"Not OTSL" and "the table is empty" are different answers."""
    assert otsl.grid("<table><tr><td>x</td></tr></table>") is None
    assert otsl.grid("просто проза") is None
    assert otsl.grid("") is None


def test_sniffed_kind_never_overrides_the_declared_one():
    """A guess at the kind lies BESIDE and decides nothing."""
    assert vrun._sniff("<fcel>a<nl>") == "otsl"
    assert vrun._sniff("проза") == "text"
    assert vrun._sniff("") == "empty"


# ------------------------------------------------------- the book pass ---

def _png():
    """A real small picture: the transport reads bytes, not a path."""
    import tempfile
    import pymupdf
    d = os.path.join(tempfile.mkdtemp(), "к.png")
    doc = pymupdf.open()
    pg = doc.new_page(width=60, height=30)
    pg.insert_text((5, 20), "abc")
    pg.get_pixmap(dpi=72).save(d)
    doc.close()
    return d


def _book(tmp):
    """A tiny book and its detect directory: text, table and a picture."""
    import pymupdf
    from booksmith.run import stamp
    pdf = os.path.join(tmp, "к.pdf")
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pg.insert_text((20, 40), "строка прозы")
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
                   "raster": {"dpi": 144.0},
                   "commit": None, "adapter": {"name": "поддельный"},
                   "weights": {"layout": None}}, f, ensure_ascii=False)
    return pdf


def _run(tmp, plan, **kw):
    out = os.path.join(tmp, "read")
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        os.environ["MODEL_NAME"] = s.model
        r = PaddleOcrVl("PP-DocLayoutV2")
        t = vrun.read_book(os.path.join(tmp, "detect"), out, r, vhttp.Http(),
                           log=lambda *a: None, **kw)
    return out, t


def test_read_fills_content_in_the_same_page_schema():
    """Reading produces the same `pages/*.json` detection does."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "строка прозы"},
                        "Table Recognition:": {"text": "<fcel>А<fcel>Б<nl>"}})
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    by = {b.block_id: b for b in p.blocks}
    assert by[0].content == "строка прозы" and by[0].kind == "text"
    assert by[1].content == "<fcel>А<fcel>Б<nl>" and by[1].kind == "otsl"
    # The picture was never asked -- and that is NOT model silence.
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
    dirt = "  <b>не закрыт &amp;\n\tпробелы  "
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
    out, _ = _run(tmp, {"OCR:": {"text": "проза"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with open(os.path.join(out, "answers", "p0000.json"), encoding="utf-8") as f:
        a = {x["anchor"]: x for x in json.load(f)["answers"]}
    assert a["p0000-b0"]["observed"]["kind_sniffed"] == "text"
    assert a["p0000-b1"]["observed"]["kind_sniffed"] == "otsl"
    assert "seconds" in a["p0000-b0"]
    # And not one mark of ours in the text itself.
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    assert p.blocks[0].content == "проза"


def test_swapped_pdf_stops_the_run():
    """A book swapped after detection drops the reading, aloud."""
    import tempfile
    tmp = tempfile.mkdtemp()
    pdf = _book(tmp)
    with open(pdf, "ab") as f:
        f.write(b"% extra byte\n")   # no non-ASCII byte goes in a b"" literal
    try:
        _run(tmp, {"OCR:": {"text": "x"}})
    except SystemExit as e:
        assert "sha256" in str(e)
    else:
        raise AssertionError("чтение пошло по подменённой книге")


def test_resume_does_not_ask_twice():
    """Resuming does not pay twice for a block already read."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    plan = {"OCR:": {"text": "проза"},
            "Table Recognition:": {"text": "<fcel>a<nl>"}}
    out, t1 = _run(tmp, plan)
    assert t1["reused_from_previous_run"] == 0
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        t2 = vrun.read_book(os.path.join(tmp, "detect"), out,
                            PaddleOcrVl("PP-DocLayoutV2"), vhttp.Http(),
                            resume=True, log=lambda *a: None)
        assert len(s.seen) == 0, f"переспрошено {len(s.seen)} блоков"
    assert t2["reused_from_previous_run"] == 2


def test_empty_run_is_not_a_success():
    """Zero blocks asked is not a success but an empty run."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    try:
        _run(tmp, {"OCR:": {"text": "x"}}, pages_want={999})
    except SystemExit as e:
        assert "пуст" in str(e)
    else:
        raise AssertionError("пустой набор страниц прошёл молча")


def test_snapshot_carries_prompts_and_our_parser():
    """The snapshot carries prompts, generation and the hash of OUR OTSL
    parser.

    Prompts are the only thing here that steers the answer, and the "prompts"
    field was empty in every run of the project until now. The OTSL parser is
    hashed apart: it decides the numbers no less than the model, and two runs
    with different parsers must differ in the snapshot.
    """
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "проза"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with FakeVlm({"text": "x"}) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        p = vrun.snapshot(os.path.join(tmp, "detect"), out,
                          PaddleOcrVl("PP-DocLayoutV2"), vhttp.Http(), t,
                          {"detect": "detect", "out": out})
    with open(p, encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["prompts"]["table"] == "Table Recognition:"
    assert snap["generation"]["max_tokens"] == 4096
    assert len(snap["adapter"]["sha256_otsl_parser"]) == 64
    assert snap["fingerprint"]["weights"]["dir"] is None
    # The key does NOT go into the snapshot: snapshots are committed to git.
    assert snap["transport_fingerprint"]["api_key"] == "no"
