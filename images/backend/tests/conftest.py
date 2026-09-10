import json
import os
from dataclasses import dataclass

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend import knobs
from backend.identity import sha256
from fake_layout import FakeLayout
from fake_metrics import FakeMetrics

PAGES = 3
DPI = float(knobs.KNOB["PAGE_DPI"].default)
K = DPI / 72.0


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
            page.insert_text((40, 60 + 18 * k), f"page {i} line {k} of the book", fontsize=11)
        page.draw_rect(pymupdf.Rect(60, 300, 340, 420), color=(0, 0, 0), fill=(0.3, 0.3, 0.3))
        page.insert_text((60, 480), f"caption {i}", fontsize=9)
    doc.save(pdf)
    doc.close()
    for i in range(PAGES):
        def box(x0, y0, x1, y1):
            return [round(v * K, 1) for v in (x0, y0, x1, y1)]

        truth = {"index": i, "width": int(400 * K), "height": int(600 * K), "dpi": DPI,
                 "blocks": [{"block_id": 0, "box": box(36, 46, 250, 160), "label": "text", "score": None,
                             "order": 0, "content": "\n".join(f"page {i} line {k} of the book" for k in range(6)),
                             "kind": "text"},
                            {"block_id": 1, "box": box(60, 300, 340, 420), "label": "table", "score": None,
                             "order": 1, "content": None, "kind": "none"},
                            {"block_id": 2, "box": box(56, 470, 130, 486), "label": "figure_title", "score": None,
                             "order": 2, "content": f"caption {i}", "kind": "text"}],
                 "meta": {"text_marked": True, "order_marked": True}}
        with open(os.path.join(root, "truth", f"{i:04d}.json"), "w", encoding="utf-8") as f:
            json.dump(truth, f)
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"book": os.path.basename(root), "source": {"name": "book.pdf", "sha256": sha256(pdf)}}, f)
    return Bench(root, pdf, os.path.join(root, "truth"))


@pytest.fixture(scope="session")
def bench(tmp_path_factory):
    return make_bench(str(tmp_path_factory.mktemp("bench") / "tiny"))


@pytest.fixture(scope="session")
def served_endpoint(bench):
    with FakeLayout(bench.truth_dir) as fake:
        yield fake.url


@pytest.fixture(scope="session")
def metrics():
    with FakeMetrics() as fake:
        yield fake


@pytest.fixture
def home(tmp_path, monkeypatch, metrics):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("BOOKSMITH_HOME", str(h))
    monkeypatch.setenv("BOOKSMITH_WORKERS", "1")
    monkeypatch.setenv("BOOKSMITH_METRICS", metrics.url)
    return str(h)


@pytest.fixture
def app(home):
    from backend.app import create_app
    from backend.settings import Settings

    a = create_app(Settings.from_env())
    yield a
    a.state.db.close()


def as_user(app, name, password="pw", role="user"):
    if app.state.db.user(name) is None:
        user_id = auth.add_user(app.state.db, name, password, role)
        app.state.settings.store_of(user_id, role)
    c = TestClient(app)
    r = c.post("/api/login", json={"name": name, "password": password})
    assert r.status_code == 200, r.text
    return c


def wait_done(client, job_id, timeout=120.0):
    lines, last = [], None
    with client.stream("GET", f"/api/jobs/{job_id}/events", timeout=timeout) as r:
        for raw in r.iter_lines():
            if not raw.startswith("data: "):
                continue
            ev = json.loads(raw[6:])
            if ev.get("event") == "line":
                lines.append(ev)
            elif ev.get("event") == "state":
                last = ev
                if ev.get("state") in ("done", "failed", "cancelled"):
                    break
    return lines, last
