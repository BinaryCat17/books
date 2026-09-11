import glob
import json
import os
import time

import jsonschema

from backend import raster, schema, settings, store
from backend.errors import Refusal
from backend.page import load_pages, write_json

LAYERS = "truth.layers"


def pages(truth_dir: str) -> dict:
    out = load_pages(truth_dir, "truth")
    layers = os.path.join(os.path.dirname(truth_dir.rstrip("/")), LAYERS)
    if os.path.isdir(layers):
        for name in sorted(os.listdir(layers)):
            if name.endswith(".json"):
                with open(os.path.join(layers, name), encoding="utf-8") as f:
                    p = json.load(f)
                out[int(p["index"])] = p
    return out


def write_layer(truth_dir: str, page: dict, author: str) -> str:
    try:
        schema.validate(page, "page.schema.json")
    except jsonschema.ValidationError as e:
        raise Refusal(f"not a page: {e.message}") from None
    when = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    page = {**page, "meta": {**(page.get("meta") or {}), "author": author, "when": when}}
    layers = os.path.join(os.path.dirname(truth_dir.rstrip("/")), LAYERS)
    os.makedirs(layers, exist_ok=True)
    path = os.path.join(layers, f"{int(page['index']):04d}-{when}-{store.safe_label(author, 'author')}.json")
    write_json(path, page, indent=1)
    return path


def blank(book_dir: str, pdf: str, dpi: float) -> str:
    truth_dir = os.path.join(book_dir, "truth")
    if os.path.isdir(truth_dir):
        raise Refusal("this book already has truth")
    os.makedirs(truth_dir)
    with raster.open_pdf(pdf) as doc:
        for i, pg in enumerate(doc):
            w, h = pg.rect.width * dpi / 72.0, pg.rect.height * dpi / 72.0
            write_json(os.path.join(truth_dir, f"{i:04d}.json"),
                       {"index": i, "width": int(w), "height": int(h), "dpi": dpi, "blocks": [],
                        "meta": {"labelled": False, "text_marked": False, "order_marked": False}}, indent=1)
    return truth_dir


def borrowed(sha256: str | None) -> str | None:
    if not sha256:
        return None
    for man in sorted(glob.glob(os.path.join(settings.home(), "bench", "*", "manifest.json"))):
        try:
            with open(man, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        truth = os.path.join(os.path.dirname(man), "truth")
        if (d.get("source") or {}).get("sha256") == sha256 and os.path.isdir(truth):
            return truth
    return None


def of(b: store.Book) -> str | None:
    return b.truth_dir or borrowed(b.sha256)


def page(truth_dir: str, index: int) -> dict:
    got = pages(truth_dir).get(int(index))
    if got is None:
        raise Refusal(f"no page {index} in the truth")
    return got


def relative(truth_dir: str) -> str:
    return os.path.relpath(truth_dir, settings.home())
