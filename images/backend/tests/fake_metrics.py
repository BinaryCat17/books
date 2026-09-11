import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.page import anchor, load_pages
from backend.truth import fingerprint, pages as truth_pages

CATALOG = [
    {
        "metric": "fitness",
        "needs": ["pages", "pdf"],
        "description": "fake",
        "scalars": [
            {
                "name": "ink_under_boxes",
                "better": "higher",
                "gloss": "ink under boxes",
                "question": "",
                "per": "page",
                "side": "",
                "unit": "",
            }
        ],
    },
    {
        "metric": "contour",
        "needs": ["pages", "truth"],
        "description": "fake",
        "scalars": [
            {
                "name": "artefacts_found",
                "better": "higher",
                "gloss": "found",
                "question": "",
                "per": "block",
                "side": "truth",
                "unit": "",
            }
        ],
    },
]


def _run_dir(body):
    home = os.environ["BOOKSMITH_HOME"]
    return os.path.join(home, body["store"], body["book"], body["kind"], body["run"])


def _truth_dir(body):
    if body.get("truth"):
        return os.path.join(os.environ["BOOKSMITH_HOME"], body["truth"])
    return os.path.join(os.path.dirname(os.path.dirname(_run_dir(body))), "truth")


def measure(body):
    rd = _run_dir(body)
    if not os.path.isfile(os.path.join(rd, "run.json")):
        return 409, {"error": f"no run {body['kind']}/{body['run']}"}
    with open(os.path.join(rd, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    pages = load_pages(os.path.join(rd, "pages"))
    want = body.get("pages")
    if want is not None and set(want) - set(pages):
        return 409, {"error": "no such pages"}
    idx = sorted(want) if want is not None else sorted(pages)
    base = {
        "bench": os.path.basename(body["book"]),
        "run": body["run"],
        "book": body["book"],
        "identity": snap.get("identity"),
        "source_sha256": snap["source"]["sha256"],
        "params": {},
        "detail": {},
    }
    recs = [
        {
            **base,
            "metric": "fitness",
            "scalars": {"ink_under_boxes": {"value": 0.5, "per": {anchor(i): 0.5 for i in idx}}},
        }
    ]
    if os.path.isdir(_truth_dir(body)):
        base["truth_sha256"] = fingerprint(_truth_dir(body))
        recs = [{**r, "truth_sha256": base["truth_sha256"]} for r in recs]
        recs.append(
            {
                **base,
                "metric": "contour",
                "scalars": {
                    "artefacts_found": {"value": 1.0, "count": {"n": 1, "of": 1}, "per": {anchor(i, 1): 1.0 for i in idx}, "side": "truth"}
                },
                "detail": {"by_label": {"table": {"found": 1}}},
            }
        )
    only = body.get("only")
    if only:
        recs = [r for r in recs if r["metric"] in only]
    return 200, {"records": recs}


def pairs(body):
    rd = _run_dir(body)
    i = int(body["index"])
    truth = truth_pages(_truth_dir(body))
    run = load_pages(os.path.join(rd, "pages"))
    if i not in truth or i not in run:
        return 409, {"error": f"no page {i}"}
    t, m = truth[i], run[i]
    by = {b["block_id"]: b for b in m["blocks"]}
    out, seen = [], set()
    for b in t["blocks"]:
        x = by.get(b["block_id"])
        ta = anchor(i, b["block_id"])
        if x is None:
            out.append(
                {
                    "truth": ta,
                    "verdict": "missed",
                    "by": "A",
                    "run": None,
                    "label_ok": None,
                    "why": "not seen",
                    "fate": "not_seen",
                    "b_run": None,
                    "b_label_ok": None,
                }
            )
        else:
            seen.add(b["block_id"])
            ra = anchor(i, x["block_id"])
            out.append(
                {
                    "truth": ta,
                    "verdict": "matched",
                    "by": "A",
                    "run": ra,
                    "label_ok": b["label"] == x["label"],
                    "why": None,
                    "fate": "intact",
                    "b_run": ra,
                    "b_label_ok": b["label"] == x["label"],
                }
            )
    extras = [
        {"run": anchor(i, x["block_id"]), "verdict": "spurious_box", "taken_for": None}
        for x in m["blocks"]
        if x["block_id"] not in seen
    ]
    meta = t.get("meta") or {}
    state = "not_said" if "labelled" not in meta else ("yes" if meta["labelled"] else "no")
    return 200, {"index": i, "labelled": state, "compared": state != "no", "pairs": out, "extras": extras}


class FakeMetrics:
    def __init__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path == "/metrics":
                    return self._json(200, CATALOG)
                self._json(404, {"error": "no route"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                fake.seen.append((self.path, body))
                if self.path == "/measure":
                    return self._json(*measure(body))
                if self.path == "/pairs":
                    return self._json(*pairs(body))
                self._json(404, {"error": "no route"})

        self.seen = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()
