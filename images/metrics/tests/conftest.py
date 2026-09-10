import json
import os
import shutil
from dataclasses import dataclass

import pymupdf
import pytest

from metrics import knobs
from metrics.identity import identity, sha256
from metrics.page import write_json

PAGES = 3
DPI = float(knobs.KNOB["PAGE_DPI"].default)
K = DPI / 72.0
POLICY = {"vocabulary": "PP-DocLayoutV2"}


@dataclass
class Bench:
    root: str
    pdf: str
    truth_dir: str
    pages: int = PAGES


def make_bench(root: str) -> Bench:
    os.makedirs(os.path.join(root, "truth"))
    pdf = os.path.join(root, "book.pdf")
    doc = pymupdf.open()
    for i in range(PAGES):
        page = doc.new_page(width=400, height=600)
        for k in range(6):
            page.insert_text((40, 60 + 30 * i + 18 * k), f"page {i} line {k} of the book", fontsize=11)
        page.draw_rect(pymupdf.Rect(60, 300 + 30 * i, 340, 420 + 30 * i), color=(0, 0, 0), fill=(0.3, 0.3, 0.3))
        page.insert_text((60, 500 + 30 * i), f"caption {i}", fontsize=9)
    doc.save(pdf)
    doc.close()

    def box(x0, y0, x1, y1):
        return [round(v * K, 1) for v in (x0, y0, x1, y1)]

    for i in range(PAGES):
        truth = {
            "index": i, "width": int(400 * K), "height": int(600 * K), "dpi": DPI,
            "blocks": [
                {"block_id": 0, "box": box(36, 46 + 30 * i, 250, 160 + 30 * i), "label": "text", "score": None, "order": 0,
                 "content": "\n".join(f"page {i} line {k} of the book" for k in range(6)), "kind": "text"},
                {"block_id": 1, "box": box(60, 300 + 30 * i, 340, 420 + 30 * i), "label": "table", "score": None, "order": 1,
                 "content": None, "kind": "none"},
                {"block_id": 2, "box": box(56, 490 + 30 * i, 130, 506 + 30 * i), "label": "figure_title", "score": None,
                 "order": 2, "content": f"caption {i}", "kind": "text"},
            ],
            "meta": {"text_marked": True, "order_marked": True},
        }
        write_json(os.path.join(root, "truth", f"{i:04d}.json"), truth)
    write_json(os.path.join(root, "manifest.json"),
               {"book": os.path.basename(root), "source": {"name": "book.pdf", "sha256": sha256(pdf)}})
    return Bench(root, pdf, os.path.join(root, "truth"))


def run_of_truth(bench: Bench, label: str = "truth", kind: str = "detect") -> str:
    rd = os.path.join(bench.root, kind, label)
    shutil.copytree(bench.truth_dir, os.path.join(rd, "pages"))
    for name in os.listdir(os.path.join(rd, "pages")):
        p = os.path.join(rd, "pages", name)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["meta"] = {"reading_order": "own"}
        write_json(p, d)
    fp = {"sha256_weights": "0" * 64, "name": label}
    write_json(os.path.join(rd, "run.json"), {
        "when": "2026-09-10T00:00:00+0000", "label": label, "identity": identity(fp, {"PAGE_DPI": str(DPI)}),
        "commit": None, "source": {"path": bench.pdf, "sha256": sha256(bench.pdf)},
        "raster": {"dpi": DPI, "scale": K}, "knobs": {}, "fingerprint": fp, "policy": POLICY,
        "served": None, "adapter": {"name": label}, "args": {},
    })
    return rd


@pytest.fixture(scope="session")
def home(tmp_path_factory):
    h = str(tmp_path_factory.mktemp("home"))
    os.environ["BOOKSMITH_HOME"] = h
    return h


@pytest.fixture(scope="session")
def bench(home):
    b = make_bench(os.path.join(home, "bench", "tiny"))
    run_of_truth(b)
    return b
