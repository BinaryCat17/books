"""The routes. Every one takes names, never paths: a book is `bench/<x>` or
`processed/<x>` as the store lists it, a run its kind and label, and the
store is the user's own, derived from the session. A refusal from the
service is a status with its text; an anonymous request is a 401.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from booksmith import service
from booksmith.core.errors import Refusal
from booksmith.web import auth
from booksmith.web.db import as_dict
from booksmith.web.jobs import KINDS

router = APIRouter(prefix="/api")


def _store(request: Request, user: dict) -> str:
    return request.app.state.settings.store_of(user["id"], user["role"])


def _book(root: str, name: str) -> str:
    if root not in ("bench", "processed") or "/" in name or name in ("", ".", ".."):
        raise Refusal(f"a book is bench/<name> or processed/<name>, not {root}/{name}")
    return f"{root}/{name}"


# ------------------------------------------------------------------- who
class Login(BaseModel):
    name: str
    password: str


@router.post("/login")
def login(body: Login, request: Request, response: Response) -> dict:
    db = request.app.state.db
    token = auth.login(db, body.name, body.password,
                       request.app.state.settings.session_days)
    if token is None:
        response.status_code = 401
        return {"error": "no such user and password"}
    s = request.app.state.settings
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax",
                        secure=s.secure_cookies, max_age=s.session_days * 86400)
    return auth.who(db, token) or {}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    auth.logout(request.app.state.db, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    return auth.require(request)


# ----------------------------------------------------------------- books
@router.get("/books")
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
    # The scan lands in a temporary file under the store's raw/ and becomes
    # a book from there, checked before anything is placed; the copy beside
    # the manifest is the book's, and nothing else of it is kept.
    fd, tmp = tempfile.mkstemp(prefix=".upload.", dir=raw)
    try:
        with os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(file.file, f)
        dest = service.upload(store, tmp, name, filename=file.filename or "")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"book": os.path.relpath(dest, store), "runs": []}


@router.get("/books/{root}/{name}/runs")
def runs(root: str, name: str, request: Request) -> list[dict]:
    user = auth.require(request)
    return service.runs(_store(request, user), _book(root, name))


@router.get("/books/{root}/{name}/pages/{index}/image")
def page_image(root: str, name: str, index: int, request: Request,
               dpi: float = 110.0) -> Response:
    user = auth.require(request)
    png = service.page_image(_store(request, user), _book(root, name), index, dpi)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/books/{root}/{name}/runs/{kind}/{label}")
def run(root: str, name: str, kind: str, label: str, request: Request) -> dict:
    user = auth.require(request)
    return service.run(_store(request, user), _book(root, name), kind, label)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/pages/{index}")
def page(root: str, name: str, kind: str, label: str, index: int,
         request: Request) -> dict:
    user = auth.require(request)
    return service.page(_store(request, user), _book(root, name), kind, label, index)


@router.get("/books/{root}/{name}/runs/{kind}/{label}/pages/{index}/pairs")
def pairs(root: str, name: str, kind: str, label: str, index: int,
          request: Request) -> dict:
    """The metric's verdicts on the page; the truth side only for an admin."""
    user = auth.require(request)
    return service.pairs(_store(request, user), _book(root, name), kind, label,
                         index, truth_side=user["role"] == "admin")


@router.get("/books/{root}/{name}/runs/{kind}/{label}/crops/{anchor}")
def crop(root: str, name: str, kind: str, label: str, anchor: str,
         request: Request) -> Response:
    user = auth.require(request)
    png = service.crop_png(_store(request, user), _book(root, name), kind, label, anchor)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/books/{root}/{name}")
def delete_book(root: str, name: str, request: Request) -> dict:
    user = auth.require(request)
    store = _store(request, user)
    d = service.book_dir(store, _book(root, name))
    shutil.rmtree(d)
    return {"deleted": _book(root, name)}


# ------------------------------------------------------------------ jobs
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
    service.book_dir(store, body.book)      # refuses a book not in this store
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


@router.get("/jobs")
def jobs(request: Request) -> list[dict]:
    user = auth.require(request)
    rows = request.app.state.db.jobs(None if user["role"] == "admin" else user["id"])
    return [d for d in (as_dict(r) for r in rows) if d is not None]


@router.get("/jobs/{job_id}")
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

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- admin
@router.get("/models")
def models(request: Request) -> dict:
    auth.require(request, "admin")
    return service.models()


@router.put("/models")
def put_models(body: dict, request: Request) -> dict:
    auth.require(request, "admin")
    return service.write_models(body)


@router.get("/models/presets")
def presets(request: Request) -> list[dict]:
    """What a user may pick: the entries by name and kind, keys withheld."""
    auth.require(request)
    return [{"name": n, "kind": e["kind"], "knobs": e["knobs"]}
            for n, e in service.models().items()]


class NewUser(BaseModel):
    name: str
    password: str
    role: str = "user"


@router.get("/users")
def users(request: Request) -> list[dict]:
    auth.require(request, "admin")
    return [d for d in (as_dict(r) for r in request.app.state.db.users()) if d is not None]


@router.post("/users")
def add_user(body: NewUser, request: Request) -> dict:
    auth.require(request, "admin")
    user_id = auth.add_user(request.app.state.db, body.name, body.password, body.role)
    request.app.state.settings.store_of(user_id, body.role)
    return {"id": user_id, "name": body.name, "role": body.role}
