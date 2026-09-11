import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import metrics as registry
from metrics import contour, job, settings, table
from metrics import store as book_mod
from metrics.base import run_probes
from metrics.bench import Bench, Run, labelled_of, labelled_said
from metrics.errors import BooksmithError, Refusal, Unmeasurable
from metrics.page import load_pages


class Ask(BaseModel):
    store: str = ""
    book: str
    kind: str = "detect"
    run: str
    truth: str | None = None
    pages: list[int] | None = None
    only: list[str] | None = None


class PairsAsk(BaseModel):
    store: str = ""
    book: str
    kind: str = "detect"
    run: str
    truth: str | None = None
    index: int


def _open(a: Ask | PairsAsk) -> tuple[Bench, Run]:
    home = os.path.realpath(settings.home())
    root = os.path.realpath(os.path.join(home, a.store, a.book))
    if not (root == home or root.startswith(home + os.sep)) or not os.path.isdir(root) or root == home:
        raise Refusal(f"no book {a.book}")
    if a.truth:
        truth = os.path.realpath(os.path.join(home, a.truth))
        if not truth.startswith(home + os.sep) or not os.path.isdir(truth):
            raise Refusal(f"no truth {a.truth}")
        b = Bench.borrowing(root, truth)
    elif os.path.isdir(os.path.join(root, "truth")):
        b = Bench.open(root)
    else:
        b = Bench.no_truth(root)
    if a.kind not in book_mod.KINDS:
        raise Refusal(f"{a.kind!r} is not a kind of run")
    run_dir = os.path.join(root, a.kind, book_mod.safe_label(a.run, a.kind))
    return b, Run.open(run_dir)


def create_app() -> FastAPI:
    app = FastAPI(title="metrics")

    @app.exception_handler(Refusal)
    def _refusal(_r: Request, e: Refusal) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.exception_handler(Unmeasurable)
    def _unmeasurable(_r: Request, e: Unmeasurable) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=422)

    @app.exception_handler(BooksmithError)
    def _other(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/metrics")
    def catalog() -> list[dict]:
        return registry.catalog()

    @app.post("/measure")
    def measure(a: Ask) -> dict:
        b, r = _open(a)
        with job.Job().active():
            recs = table.rows(b, r, a.only, a.pages)
        return {"records": [rec.to_json() for rec in recs]}

    @app.post("/pairs")
    def pairs(a: PairsAsk) -> dict:
        b, r = _open(a)
        if not b.truth_dir:
            raise Refusal(f"{a.book} has no truth")
        truth = b.pages()
        run = load_pages(r.pages_dir, "run")
        if a.index not in truth or a.index not in run:
            raise Refusal(f"no page {a.index} on both sides")
        res = contour.page_pairs(
            truth[a.index], run[a.index], b.policy, r.policy, said=labelled_said(labelled_of(truth))
        )
        state = labelled_of({a.index: truth[a.index]})
        labelled = next(s for s, n in state.items() if n)
        return {
            "index": a.index,
            "labelled": labelled,
            "compared": res is not None,
            "pairs": list((res or {}).get("pairs", [])),
            "extras": list((res or {}).get("extras", [])),
        }

    @app.post("/probe")
    def probe(a: Ask) -> dict:
        b, r = _open(a)
        out = {}
        with job.Job().active():
            for m in registry.METRICS:
                if a.only and m.name not in a.only:
                    continue
                try:
                    probes = m.probes(b, r)
                except Unmeasurable as e:
                    out[m.name] = {"skipped": str(e)}
                    continue
                seen, mute, bad = run_probes(probes)
                out[m.name] = {"probes": seen, "no_data": mute, "uncaught": bad}
        return out

    return app
