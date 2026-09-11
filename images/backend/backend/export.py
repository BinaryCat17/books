import base64
import html as _html
import re
from collections.abc import Callable, Iterator

from backend.errors import Refusal

FORMATS = {
    "html": ("text/html; charset=utf-8", "html"),
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "text": ("text/plain; charset=utf-8", "txt"),
}
MATH = ("cdn", "off")
MATHJAX = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js"
CSS = (
    "body{max-width:52em;margin:2em auto;padding:0 1em;font:16px/1.55 Georgia,serif}"
    "figure{margin:1.2em 0}figure img{max-width:100%;height:auto;display:block;border:1px solid #ddd}"
    "figcaption{font:12px/1.4 monospace;color:#777}[data-role=furniture]{opacity:.55}"
    "[data-truncated]{border-left:3px solid #c00;padding-left:.8em}"
    "hr{border:0;border-top:1px dashed #ccc;margin:2.5em 0}"
    "table{border-collapse:collapse;font-size:.92em}th,td{border:1px solid #bbb;padding:.28em .5em;vertical-align:top}"
    "pre{white-space:pre-wrap}"
)
CUT = "cut off by the length ceiling"
_SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
Crop = Callable[[dict], bytes]


def render(fmt: str, doc: dict, crop: Crop, math: str = "cdn") -> Iterator[str]:
    if fmt not in FORMATS:
        raise Refusal(f"no export named {fmt!r}; there are {', '.join(FORMATS)}")
    if math not in MATH:
        raise Refusal(f"math is one of {', '.join(MATH)}, not {math!r}")
    return {"html": _html_doc, "markdown": _markdown, "text": _text}[fmt](doc, crop, math)


def blocks_of(page: dict) -> list[dict]:
    kept = [b for b in page["blocks"] if b["repeat_verdict"] != "verbatim"]
    return sorted(kept, key=lambda b: (b["order"] is None, b["order"] or 0))


def _uri(crop: Crop, b: dict) -> str:
    return "data:image/png;base64," + base64.b64encode(crop(b)).decode()


def _esc(s: str) -> str:
    return _html.escape(s, quote=True)


def _block_html(b: dict, crop: Crop) -> str:
    attrs = f' id="{b["anchor"]}" data-role="{b["role"]}" data-label="{_esc(b["label"])}"'
    if b["hit_ceiling"]:
        attrs += ' data-truncated="yes"'
    if b["as_picture"]:
        cap = b["label"] + (f" · {b['why_empty']}" if b["why_empty"] else "") + (f" · in {b['inside']}" if b["inside"] else "")
        return f'<figure{attrs}><img src="{_uri(crop, b)}" alt="{_esc(b["label"])}"><figcaption>{_esc(cap)}</figcaption></figure>'
    c, k = (b["content"], b["kind"])
    if k == "html":
        return f"<div{attrs}>{_SCRIPT.sub('', c)}</div>"
    if k == "latex":
        return f"<p{attrs}>\\[{_esc(c)}\\]</p>"
    if k == "otsl":
        return f"<pre{attrs}>{_esc(c)}</pre>"
    return f"<p{attrs}>{_esc(c)}</p>"


def _html_doc(doc: dict, crop: Crop, math: str) -> Iterator[str]:
    formulas = any(b["kind"] == "latex" and not b["as_picture"] for p in doc["pages"] for b in p["blocks"])
    head = f'<!doctype html>\n<html><head><meta charset="utf-8"><title>{_esc(doc["source"]["name"])}</title><style>{CSS}</style>'
    if math == "cdn" and formulas:
        head += f'<script src="{MATHJAX}" async></script>'
    yield head + "</head>\n<body>\n"
    for p in doc["pages"]:
        yield f'<hr data-page="{p["index"]}"' + (f' data-trouble="{p["trouble"]}"' if p["trouble"] else "") + ">\n"
        for b in blocks_of(p):
            yield _block_html(b, crop) + "\n"
    yield "</body></html>\n"


def _block_md(b: dict, crop: Crop) -> str | None:
    if b["role"] == "furniture":
        return None
    if b["as_picture"]:
        return f"![{b['label']}]({_uri(crop, b)})"
    c, k = (b["content"], b["kind"])
    out = f"$$\n{c}\n$$" if k == "latex" else _SCRIPT.sub("", c) if k == "html" else f"```otsl\n{c}\n```" if k == "otsl" else c
    return out + (f"\n\n*({CUT})*" if b["hit_ceiling"] else "")


def _markdown(doc: dict, crop: Crop, math: str) -> Iterator[str]:
    yield f"# {doc['source']['name']}\n"
    for p in doc["pages"]:
        yield f"\n<!-- page {p['index']} -->\n"
        for b in blocks_of(p):
            md = _block_md(b, crop)
            if md is not None:
                yield "\n" + md + "\n"


def _plain(c: str) -> str:
    def cell(m: re.Match) -> str:
        tag = m.group(0).lower()
        return "\n" if tag.startswith("</tr") else "\t" if tag.startswith(("</td", "</th")) else ""

    text = _html.unescape(_TAG.sub(cell, _SCRIPT.sub("", c)))
    return "\n".join(line.rstrip("\t") for line in text.split("\n")).strip()


def _block_txt(b: dict) -> str | None:
    if b["role"] == "furniture" or b["as_picture"]:
        return None
    c = _plain(b["content"]) if b["kind"] == "html" else b["content"]
    return c + (f"\n[{CUT}]" if b["hit_ceiling"] else "")


def _text(doc: dict, crop: Crop, math: str) -> Iterator[str]:
    for p in doc["pages"]:
        for b in blocks_of(p):
            t = _block_txt(b)
            if t is not None:
                yield t + "\n\n"
