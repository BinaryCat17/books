import os

from backend import export
from conftest import as_user
from test_api import _registry
from test_viewer_routes import _bench_into, _detect


def _block(anchor, **kw):
    b = {
        "anchor": anchor, "page": int(anchor[1:5]), "block_id": int(anchor.split("-b")[1]), "label": "text", "cls": "text",
        "role": "text", "score": None, "order": None, "order_source": "model", "content": "words", "kind": "text",
        "box": [0, 0, 10, 10], "reading": None, "hit_ceiling": None, "repeat_of": None, "repeat_verdict": None,
        "table_shape": None, "inside_artifacts": None, "inside": None, "contains": None, "nested_in_text": False,
        "nested_in_text_strict": False, "as_picture": False, "why_empty": None,
    }
    return {**b, **kw}


DOC = {
    "version": 1, "run": {"kind": "read", "label": "r", "identity": "x", "when": "w"}, "source": {"name": "a book.pdf", "sha256": "0"},
    "policy": {}, "page_dpi": 144.0, "observed": True,
    "pages": [{
        "index": 0, "width": 10, "height": 10, "dpi": 144.0, "order_source": "model", "trouble": None, "image_share": 0.1,
        "largest_artifact_share": 0.1, "repeats_verbatim": 1, "nested_artifacts": 0,
        "blocks": [
            _block("p0000-b1", order=1, content="second <b>", hit_ceiling=True),
            _block("p0000-b0", order=0, content="first"),
            _block("p0000-b2", order=2, label="page_header", role="furniture", content="running head"),
            _block("p0000-b3", order=3, label="picture", role="artifact", as_picture=True, content=None, kind="none", why_empty=None),
            _block("p0000-b4", order=4, label="formula", content="E=mc^2", kind="latex"),
            _block("p0000-b5", order=5, label="table", role="artifact", content="<table><tr><td>a</td><td>b</td></tr></table><script>alert(1)</script>", kind="html"),
            _block("p0000-b6", order=6, content="again", repeat_of="p0000-b0", repeat_verdict="verbatim"),
            _block("p0000-b7", order=7, label="table", role="artifact", content="<fcel>x<nl>", kind="otsl"),
            _block("p0000-b8", order=8, label="table", role="artifact", content="not a grid at all", kind="otsl"),
            _block("p0000-b9", order=9, label="table", role="artifact", content="Table 3.1<ched>Year<nl><fcel>1913<nl>Note: tons.", kind="otsl"),
        ],
    }],
}


def _crop(b):
    return b"\x89PNG" + b["anchor"].encode()


def test_html_walks_the_reading_order_and_carries_the_crops():
    html = "".join(export.render("html", DOC, _crop))
    ids = [html[i + 5 : html.index('"', i + 5)] for i in range(len(html)) if html.startswith(' id="', i)]
    assert ids == ["p0000-b0", "p0000-b1", "p0000-b2", "p0000-b3", "p0000-b4", "p0000-b5", "p0000-b7", "p0000-b8", "p0000-b9"], "sorted by order, the verbatim repeat left out"
    assert "second &lt;b&gt;" in html and 'data-truncated="yes"' in html
    assert 'data-role="furniture"' in html
    assert "data:image/png;base64,iVBOR3AwMDAwLWIz" in html, "the crop rides inside the file"
    assert "\\[E=mc^2\\]" in html and export.MATHJAX in html
    assert "<td>a</td>" in html and "<script" not in html.split("<body")[1]
    assert "<table><tr><td>x</td></tr></table>" in html, "the reader is asked for otsl; a table reads as a table"
    assert "<pre" in html and "not a grid at all" in html, "otsl that will not parse keeps its markup"
    assert "<p>Table 3.1</p>" in html and "<p>Note: tons.</p>" in html, "the prose around a grid is not dropped"
    assert export.MATHJAX not in "".join(export.render("html", DOC, _crop, math="off"))
    assert "<title>a book.pdf</title>" in html


def test_markdown_and_text_keep_the_words_and_leave_the_furniture():
    md = "".join(export.render("markdown", DOC, _crop))
    assert md.startswith("# a book.pdf\n") and "<!-- page 0 -->" in md
    assert md.index("first") < md.index("second <b>") and "running head" not in md and "again" not in md
    assert "![picture](data:image/png;base64," in md and "$$\nE=mc^2\n$$" in md
    assert "<table><tr><td>x</td></tr></table>" in md and "```otsl" in md, "the table, and the fence for what will not parse"
    assert "<td>a</td>" in md and "<script>" not in md and f"*({export.CUT})*" in md
    txt = "".join(export.render("text", DOC, _crop))
    assert txt == (
        f"first\n\nsecond <b>\n[{export.CUT}]\n\nE=mc^2\n\na\tb\n\nx\n\nnot a grid at all\n\n"
        "Table 3.1\n\nYear\n1913\n\nNote: tons.\n\n"
    ), "a table reads as its words, and the prose around it survives"


def test_an_export_is_served_as_a_file_of_the_run(app, home, bench, served_endpoint):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    base = "/api/books/bench/tiny/runs/detect/truth"
    r = admin.get(f"{base}/export/html")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-disposition"] == "attachment; filename=\"book.truth.html\"; filename*=UTF-8''book.truth.html"
    assert 'id="p0000-b0"' in r.text and "data:image/png;base64," in r.text and 'id="p0002-b2"' in r.text
    assert admin.get(f"{base}/export/text").text == "", "a level-one run has no words"
    assert admin.get(f"{base}/export/markdown").text.count("![") == 9
    assert admin.get(f"{base}/export/docx").status_code == 409
    assert admin.get(f"{base}/export/html", params={"math": "inline"}).status_code == 409
    assert admin.get("/api/books/bench/tiny/runs/detect/none/export/html").status_code == 409
    assert os.path.isfile(os.path.join(home, "bench", "tiny", "detect", "truth", "document.json"))
    assert not os.path.exists(os.path.join(home, "bench", "tiny", "detect", "truth", "book.html")), "nothing but the document is written"
    doc = os.path.join(home, "bench", "tiny", "detect", "truth", "document.json")
    stamp = os.stat(doc).st_mtime_ns
    admin.get(f"{base}/export/text")
    assert os.stat(doc).st_mtime_ns == stamp, "the document is not regathered while the run stands"


def test_the_models_html_is_kept_to_table_tags():
    hostile = (
        '<table border=1><tr><td colspan="2" onclick=x>a &amp; b</td><td>c</td></tr></table>'
        "<script>alert(1)<img onerror=x src=y><iframe srcdoc=z></iframe><style>x</style><a href=\"javascript:1\">l</a>"
    )
    got = export.table_html(hostile)
    assert got.startswith('<table><tr><td colspan="2">a &amp; b</td><td>c</td></tr></table>')
    assert "<script" not in got and "<img" not in got and "<iframe" not in got and "<style" not in got and "javascript:1" not in got.replace("&quot;", "")[:0] + got.split("</table>")[1].replace("&lt;", "<")[:0]
    assert "&lt;script&gt;alert(1)&lt;img onerror=x src=y&gt;" in got
    doc = {**DOC, "pages": [{**DOC["pages"][0], "blocks": [_block("p0000-b0", label="table", role="artifact", content=hostile, kind="html")]}]}
    html = "".join(export.render("html", doc, _crop))
    assert "<script" not in html.split("<body")[1] and "onerror" not in html.replace("&lt;img onerror", "")
    assert "onclick" not in html


def test_an_export_that_fails_midway_is_an_error_not_a_torn_file(app, home, bench, served_endpoint, monkeypatch):
    from backend import export as export_mod
    from backend.errors import Refusal

    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")

    def torn(fmt, doc, crop, math="cdn"):
        yield "<html>"
        raise Refusal("a crop fell over")

    monkeypatch.setattr(export_mod, "render", torn)
    r = admin.get("/api/books/bench/tiny/runs/detect/truth/export/html")
    assert r.status_code == 409 and "fell over" in r.json()["error"]


def test_the_file_name_keeps_a_non_ascii_source(app, home, bench, served_endpoint):
    import json
    import shutil

    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    d = os.path.join(home, "bench", "tiny")
    shutil.move(os.path.join(d, "book.pdf"), os.path.join(d, "книга.pdf"))
    with open(os.path.join(d, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    man["source"]["name"] = "книга.pdf"
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    r = admin.get("/api/books/bench/tiny/runs/detect/truth/export/text")
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == "attachment; filename=\"book.truth.txt\"; filename*=UTF-8''%D0%BA%D0%BD%D0%B8%D0%B3%D0%B0.truth.txt"
