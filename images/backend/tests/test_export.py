import os

from backend import export
from conftest import as_user
from support import said
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
        ],
    }],
}


def _crop(b):
    return b"\x89PNG" + b["anchor"].encode()


def test_html_walks_the_reading_order_and_carries_the_crops():
    html = "".join(export.render("html", DOC, _crop))
    ids = [html[i + 5 : html.index('"', i + 5)] for i in range(len(html)) if html.startswith(' id="', i)]
    assert ids == ["p0000-b0", "p0000-b1", "p0000-b2", "p0000-b3", "p0000-b4", "p0000-b5", "p0000-b7"], "sorted by order, the verbatim repeat left out"
    assert "second &lt;b&gt;" in html and 'data-truncated="yes"' in html
    assert 'data-role="furniture"' in html
    assert "data:image/png;base64,iVBOR3AwMDAwLWIz" in html, "the crop rides inside the file"
    assert "\\[E=mc^2\\]" in html and export.MATHJAX in html
    assert "<td>a</td>" in html and "<script>" not in html
    assert "<pre" in html and "&lt;fcel&gt;" in html
    assert export.MATHJAX not in "".join(export.render("html", DOC, _crop, math="off"))
    assert "<title>a book.pdf</title>" in html


def test_markdown_and_text_keep_the_words_and_leave_the_furniture():
    md = "".join(export.render("markdown", DOC, _crop))
    assert md.startswith("# a book.pdf\n") and "<!-- page 0 -->" in md
    assert md.index("first") < md.index("second <b>") and "running head" not in md and "again" not in md
    assert "![picture](data:image/png;base64," in md and "$$\nE=mc^2\n$$" in md and "```otsl" in md
    assert "<td>a</td>" in md and "<script>" not in md and f"*({export.CUT})*" in md
    txt = "".join(export.render("text", DOC, _crop))
    assert txt == f"first\n\nsecond <b>\n[{export.CUT}]\n\nE=mc^2\n\na\tb\n\n<fcel>x<nl>\n\n"


def test_an_export_is_served_as_a_file_of_the_run(app, home, bench, served_endpoint):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    base = "/api/books/bench/tiny/runs/detect/truth"
    r = admin.get(f"{base}/export/html")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-disposition"] == 'attachment; filename="book.truth.html"'
    assert 'id="p0000-b0"' in r.text and "data:image/png;base64," in r.text and 'id="p0002-b2"' in r.text
    assert admin.get(f"{base}/export/text").text == "", "a level-one run has no words"
    assert admin.get(f"{base}/export/markdown").text.count("![") == 9
    assert admin.get(f"{base}/export/docx").status_code == 409
    assert admin.get(f"{base}/export/html", params={"math": "inline"}).status_code == 409
    assert admin.get("/api/books/bench/tiny/runs/detect/none/export/html").status_code == 409
    assert os.path.isfile(os.path.join(home, "bench", "tiny", "detect", "truth", "document.json"))
    assert not os.path.exists(os.path.join(home, "bench", "tiny", "detect", "truth", "book.html")), "nothing but the document is written"
    with said():
        assert True
