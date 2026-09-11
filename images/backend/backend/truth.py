import glob
import hashlib
import json
import os
import re
import time

import jsonschema

from backend import raster, schema, settings, store
from backend.errors import Refusal
from backend.page import load_pages, write_json

LAYERS = "truth.layers"
_AUTHOR = re.compile(r"[^A-Za-z0-9._-]+")


def _layers(truth_dir: str) -> str:
    return os.path.join(os.path.dirname(truth_dir.rstrip("/")), LAYERS)


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pages(truth_dir: str) -> dict:
    out = load_pages(truth_dir, "truth")
    layers = _layers(truth_dir)
    if os.path.isdir(layers):
        for name in sorted(os.listdir(layers)):
            if name.endswith(".json") and name[:4].isdigit() and int(name[:4]) in out:
                out[int(name[:4])] = _read(os.path.join(layers, name))
    return out


def page(truth_dir: str, index: int) -> dict:
    base = os.path.join(truth_dir, f"{int(index):04d}.json")
    if not os.path.isfile(base):
        raise Refusal(f"no page {index} in the truth")
    layers = sorted(glob.glob(os.path.join(_layers(truth_dir), f"{int(index):04d}-*.json")))
    return _read(layers[-1] if layers else base)


def fingerprint(truth_dir: str) -> str:
    blob = json.dumps(pages(truth_dir), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_layer(truth_dir: str, page_: dict, author: str) -> str:
    try:
        schema.validate(page_, "page.schema.json")
    except jsonschema.ValidationError as e:
        raise Refusal(f"not a page: {e.message}") from None
    index = int(page_["index"])
    if not os.path.isfile(os.path.join(truth_dir, f"{index:04d}.json")):
        raise Refusal(f"no page {index} in the truth")
    who = _AUTHOR.sub("-", author).strip("-") or "admin"
    layers = _layers(truth_dir)
    os.makedirs(layers, exist_ok=True)
    now = time.time()
    while True:
        when = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f".{int(now % 1 * 1e6):06d}Z"
        path = os.path.join(layers, f"{index:04d}-{when}-{who}.json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            break
        except FileExistsError:
            now += 1e-6
    body = {**page_, "meta": {**(page_.get("meta") or {}), "author": author, "when": when}}
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
    return path


def blank(book_dir: str, pdf: str, dpi: float) -> str:
    truth_dir = os.path.join(book_dir, "truth")
    if os.path.isdir(truth_dir):
        raise Refusal("this book already has truth")
    os.makedirs(truth_dir)
    with raster.open_pdf(pdf) as doc:
        for i, pg in enumerate(doc):
            w, h = raster.size(pg, dpi)
            write_json(
                os.path.join(truth_dir, f"{i:04d}.json"),
                {"index": i, "width": w, "height": h, "dpi": float(dpi), "blocks": [],
                 "meta": {"labelled": False, "text_marked": False, "order_marked": False}},
                indent=1,
            )
    return truth_dir


def borrowed(sha256: str | None) -> str | None:
    if not sha256:
        return None
    found = []
    for man in sorted(glob.glob(os.path.join(settings.home(), "bench", "*", "manifest.json"))):
        try:
            d = _read(man)
        except (OSError, ValueError):
            continue
        truth = os.path.join(os.path.dirname(man), "truth")
        if (d.get("source") or {}).get("sha256") == sha256 and os.path.isdir(truth):
            found.append(truth)
    if len(found) > 1:
        names = ", ".join(os.path.basename(os.path.dirname(t)) for t in found)
        raise Refusal(f"{len(found)} benches hold this scan ({names}): the truth to borrow is ambiguous")
    return found[0] if found else None


def of(b: store.Book) -> str | None:
    return b.truth_dir or borrowed(b.sha256)


def relative(truth_dir: str) -> str:
    return os.path.relpath(truth_dir, settings.home())
