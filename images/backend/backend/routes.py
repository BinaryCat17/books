from __future__ import annotations
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend import fleet, service, shapes
from backend.errors import Refusal
from backend import auth
from backend.db import as_dict
from backend.pool import KINDS

router = APIRouter(prefix="/api")


def _store(request: Request, user: dict) -> str:
    return request.app.state.settings.store_of(user["id"], user["role"])


def _book(root: str, name: str) -> str:
    if root not in ("bench", "processed") or "/" in name or name in ("", ".", ".."):
        raise Refusal(f"a book is bench/<name> or processed/<name>, not {root}/{name}")
    return f"{root}/{name}"


class Login(BaseModel):
    name: str
    password: str


@router.post("/login", response_model=shapes.User)
def login(body: Login, request: Request, response: Response) -> dict:
    db = request.app.state.db
    token = auth.login(db, body.name, body.password, request.app.state.settings.session_days)
    if token is None:
        raise HTTPException(401, "no such user and password")
    s = request.app.state.settings
    response.set_cookie(
        auth.COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=s.secure_cookies,
        max_age=s.session_days * 86400,
    )
    return auth.who(db, token) or {}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    auth.logout(request.app.state.db, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/me", response_model=shapes.User)
def me(request: Request) -> dict:
    return auth.require(request)


@router.get("/books", response_model=list[shapes.BookRow])
def books(request: Request) -> list[dict]:
    user = auth.require(request)
    store = _store(request, user)
    return [{"name": n, "runs": service.runs(store, n)} for n in service.books(store)]


@router.post("/books")
def upload(request: Request, file: UploadFile, name: str = "") -> dict:
    user = auth.require(request)
    store = _store(request, user)
    raw = os.path.join(store, "raw")
    os.makedirs(raw, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".upload.", dir=raw)
    try:
        with os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(file.file, f)
        dest = service.upload(store, tmp, name, filename=file.filename or "")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"book": os.path.relpath(dest, store), "runs": []}


@router.get("/books/{root}/{name}/runs", response_model=list[shapes.RunRow])
def runs(root: str, name: str, request: Request) -> list[dict]:
    user = auth.require(request)
    return service.runs(_store(request, user), _book(root, name))


@router.get("/books/{root}/{name}/pages/{index}/image")
def page_image(root: str, name: str, index: int, request: Request, dpi: float = 110.0) -> Response:
    user = auth.require(request)
    png = service.page_image(_store(request, user), _book(root, name), index, dpi)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/books/{root}/{name}/runs/{kind}/{label}", response_model=shapes.RunInfo)
def run(root: str, name: str, kind: str, label: str, request: Request) -> dict:
    user = auth.require(request)
    return service.run(_store(request, user), _book(root, name), kind, label)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/pages/{index}")
def page(root: str, name: str, kind: str, label: str, index: int, request: Request) -> dict:
    user = auth.require(request)
    return service.page(_store(request, user), _book(root, name), kind, label, index)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/pages/{index}/pairs")
def pairs(root: str, name: str, kind: str, label: str, index: int, request: Request) -> dict:
    user = auth.require(request)
    return service.pairs(
        request.app.state.settings,
        _store(request, user),
        _book(root, name),
        kind,
        label,
        index,
        truth_side=user["role"] == "admin",
    )


@router.get("/books/{root}/{name}/truth/pages/{index}")
def truth_page(root: str, name: str, index: int, request: Request) -> dict:
    user = auth.require(request, "admin")
    return service.truth_page(_store(request, user), _book(root, name), index)


@router.put("/books/{root}/{name}/truth/pages/{index}", response_model=shapes.Layer)
def put_truth_page(root: str, name: str, index: int, body: shapes.TruthPage, request: Request) -> dict:
    user = auth.require(request, "admin")
    page = body.model_dump(exclude_unset=True)
    return service.label_page(_store(request, user), _book(root, name), index, page, user["name"])


@router.post("/books/{root}/{name}/truth", response_model=shapes.TruthStart)
def start_truth(root: str, name: str, body: shapes.RunRef, request: Request) -> dict:
    user = auth.require(request, "admin")
    return service.start_truth(_store(request, user), _book(root, name), body.kind, body.label)


@router.get("/classes")
def classes(request: Request) -> dict:
    auth.require(request)
    return service.class_table()


@router.get("/books/{root}/{name}/runs/{kind}/{label}/export/{fmt}")
def export(root: str, name: str, kind: str, label: str, fmt: str, request: Request, math: str = "cdn") -> StreamingResponse:
    user = auth.require(request)
    body, media, filename = service.export(_store(request, user), _book(root, name), kind, label, fmt, math)
    return StreamingResponse(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/books/{root}/{name}/runs/{kind}/{label}/corrections", response_model=shapes.Corrections)
def corrections(root: str, name: str, kind: str, label: str, request: Request) -> dict:
    user = auth.require(request)
    return service.corrections(_store(request, user), _book(root, name), kind, label)


@router.post("/books/{root}/{name}/runs/{kind}/{label}/corrections", response_model=shapes.Corrections)
def correct(root: str, name: str, kind: str, label: str, body: shapes.Correction, request: Request) -> dict:
    user = auth.require(request)
    c = body.model_dump(exclude_unset=True)
    return service.correct(_store(request, user), _book(root, name), kind, label, c, user["name"])


@router.delete("/books/{root}/{name}/runs/{kind}/{label}/corrections/{n}", response_model=shapes.Corrections)
def uncorrect(root: str, name: str, kind: str, label: str, n: int, request: Request) -> dict:
    user = auth.require(request)
    return service.uncorrect(_store(request, user), _book(root, name), kind, label, n)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/results", response_model=shapes.Results)
def results(root: str, name: str, kind: str, label: str, request: Request) -> dict:
    user = auth.require(request)
    return service.results(request.app.state.db, _store(request, user), _book(root, name), kind, label)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/series", response_model=list[shapes.SeriesRow])
def series(root: str, name: str, kind: str, label: str, request: Request) -> list[dict]:
    user = auth.require(request)
    return service.series(request.app.state.db, _store(request, user), _book(root, name), kind, label)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/document")
def document(root: str, name: str, kind: str, label: str, request: Request) -> dict:
    user = auth.require(request)
    return service.document_of(_store(request, user), _book(root, name), kind, label)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/pages/{index}/metrics")
def page_metrics(root: str, name: str, kind: str, label: str, index: int, request: Request) -> list[dict]:
    user = auth.require(request)
    return service.measure_page(
        request.app.state.settings, _store(request, user), _book(root, name), kind, label, index,
        truth_side=user["role"] == "admin",
    )


@router.get("/books/{root}/{name}/runs/{kind}/{label}/crops/{anchor}")
def crop(root: str, name: str, kind: str, label: str, anchor: str, request: Request) -> Response:
    user = auth.require(request)
    png = service.crop_png(_store(request, user), _book(root, name), kind, label, anchor)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/books/{root}/{name}")
def delete_book(root: str, name: str, request: Request) -> dict:
    user = auth.require(request)
    store = _store(request, user)
    d = service.book_dir(store, _book(root, name))
    shutil.rmtree(d)
    return {"deleted": _book(root, name)}


class Start(BaseModel):
    kind: str
    book: str
    model: str = ""
    label: str = ""
    run_kind: str = "detect"
    pages: str = ""


@router.post("/jobs")
def start(body: Start, request: Request) -> dict:
    user = auth.require(request)
    store = _store(request, user)
    if body.kind not in KINDS:
        raise Refusal(f"a job is one of {KINDS}, not {body.kind!r}")
    service.book_dir(store, body.book)
    if body.model and body.model not in service.models():
        raise Refusal(f"no model {body.model!r} in the registry")
    job_id = request.app.state.pool.submit(user["id"], store, body.kind, body.model_dump())
    return {"id": job_id, "state": "queued"}


def _own(request: Request, job_id: int) -> dict:
    user = auth.require(request)
    row = as_dict(request.app.state.db.job(job_id))
    if row is None or (user["role"] != "admin" and row["user"] != user["id"]):
        raise Refusal(f"no job {job_id}")
    return row


@router.get("/jobs", response_model=list[shapes.Job])
def jobs(request: Request) -> list[dict]:
    user = auth.require(request)
    rows = request.app.state.db.jobs(None if user["role"] == "admin" else user["id"])
    return [d for d in (as_dict(r) for r in rows) if d is not None]


@router.get("/jobs/{job_id}", response_model=shapes.Job)
def one_job(job_id: int, request: Request) -> dict:
    return _own(request, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: int, request: Request) -> dict:
    _own(request, job_id)
    return {"cancelled": request.app.state.pool.cancel(job_id)}


@router.get("/jobs/{job_id}/events")
async def events(job_id: int, request: Request) -> StreamingResponse:
    _own(request, job_id)
    pool = request.app.state.pool

    async def stream() -> AsyncIterator[bytes]:
        async for ev in pool.events(job_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/models")
def models(request: Request) -> dict:
    auth.require(request, "admin")
    return service.models()


@router.put("/models")
def put_models(body: dict, request: Request) -> dict:
    auth.require(request, "admin")
    return service.write_models(body)


@router.get("/models/presets", response_model=list[shapes.Preset])
def presets(request: Request) -> list[dict]:
    auth.require(request)
    return [{"name": n, "kind": e["kind"], "knobs": e["knobs"]} for n, e in service.models().items()]


@router.get("/fleet/placements", response_model=list[shapes.Placement])
def fleet_placements(request: Request) -> list:
    auth.require(request, "admin")
    return fleet.placements()


@router.get("/fleet/ledger", response_model=list[shapes.LedgerRow])
def fleet_ledger(request: Request) -> list:
    auth.require(request, "admin")
    return fleet.ledger()


@router.delete("/fleet/placements/{pid}")
def fleet_stop(pid: str, request: Request) -> dict:
    auth.require(request, "admin")
    return fleet.stop_placement(pid)


class NewUser(BaseModel):
    name: str
    password: str
    role: str = "user"


@router.get("/users", response_model=list[shapes.User])
def users(request: Request) -> list[dict]:
    auth.require(request, "admin")
    return [d for d in (as_dict(r) for r in request.app.state.db.users()) if d is not None]


@router.post("/users", response_model=shapes.User)
def add_user(body: NewUser, request: Request) -> dict:
    auth.require(request, "admin")
    user_id = auth.add_user(request.app.state.db, body.name, body.password, body.role)
    request.app.state.settings.store_of(user_id, body.role)
    return {"id": user_id, "name": body.name, "role": body.role}
