from __future__ import annotations
import asyncio
import json
import os
import queue
import threading
import time
from collections.abc import AsyncIterator
from backend import fleet, service
from backend import job
from backend.errors import BooksmithError, Cancelled
from backend.log import log
from backend.db import TERMINAL, Db, as_dict

KINDS = ("detect", "hybrid", "read", "bench", "html")
KEEPALIVE_S = 15.0
LEASE_RENEW_S = 30.0


def run_dir_of(store: str, book: str, kind: str, label: str) -> str:
    d = os.path.join(service.book_dir(store, book), kind, label)
    if not os.path.isdir(os.path.join(d, "pages")):
        raise BooksmithError(f"{book} has no {kind} run labelled {label!r}")
    return d


def dispatch(kind: str, store: str, args: dict, base: job.Job, db: Db, cfg) -> str:
    book = str(args.get("book") or "")
    model = str(args.get("model") or "")
    label = str(args.get("label") or "")
    pages = str(args.get("pages") or "") or None
    if kind == "detect":
        return service.detect(store, service.book_dir(store, book), {}, pages, None, model, base=base)
    if kind == "hybrid":
        return service.hybrid(store, service.book_dir(store, book), {}, pages, None, model, base=base)
    if kind == "read":
        return service.read(
            store,
            run_dir_of(store, book, "detect", label),
            {},
            None,
            pages or "",
            "",
            model,
            base=base,
        )
    if kind == "bench":
        return service.bench(
            db,
            cfg,
            store,
            service.book_dir(store, book),
            run=label,
            kind=str(args.get("run_kind") or "detect"),
            base=base,
            pages=pages or "",
        )
    if kind == "html":
        return service.html(
            store,
            run_dir_of(store, book, str(args.get("run_kind") or "detect"), label),
            {},
            None,
            base=base,
        )
    raise BooksmithError(f"no such kind of job: {kind!r}; there are {KINDS}")


class Pool:
    def __init__(self, db: Db, cfg):
        self.db = db
        self.cfg = cfg
        workers = cfg.workers
        self.queue: queue.Queue[int] = queue.Queue()
        self.stops: dict[int, threading.Event] = {}
        self.listeners: dict[int, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict]]]] = {}
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []
        self.orphaned = db.orphans()
        for i in range(workers):
            t = threading.Thread(target=self._work, name=f"worker-{i}", daemon=True)
            t.start()
            self.threads.append(t)

    def submit(self, user_id: int, store: str, kind: str, args: dict) -> int:
        if kind not in KINDS:
            raise BooksmithError(f"no such kind of job: {kind!r}; there are {KINDS}")
        job_id = self.db.add_job(
            user_id,
            store,
            kind,
            str(args.get("book") or ""),
            str(args.get("label") or ""),
            str(args.get("model") or ""),
            args,
        )
        self.queue.put(job_id)
        return job_id

    def cancel(self, job_id: int) -> bool:
        with self.lock:
            stop = self.stops.get(job_id)
            if stop is not None:
                stop.set()
                return True
            row = self.db.job(job_id)
            if row is not None and row["state"] == "queued":
                self.db.set_state(job_id, "cancelled", finished=time.time())
                self._publish_locked(job_id, {"event": "state", "state": "cancelled"})
                return True
        return False

    async def events(self, job_id: int) -> AsyncIterator[dict]:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        with self.lock:
            self.listeners.setdefault(job_id, []).append((loop, q))
        try:
            row = as_dict(self.db.job(job_id))
            if row is None:
                return
            yield {"event": "state", **{k: row[k] for k in ("state", "n", "of", "error", "result")}}
            if row["state"] in TERMINAL:
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_S)
                except TimeoutError:
                    yield {"event": "keepalive"}
                    continue
                yield ev
                if ev.get("event") == "state" and ev.get("state") in TERMINAL:
                    return
        finally:
            with self.lock:
                self.listeners[job_id] = [
                    (lp, qq) for lp, qq in self.listeners.get(job_id, []) if qq is not q
                ]

    def _publish_locked(self, job_id: int, ev: dict) -> None:
        for loop, q in self.listeners.get(job_id, []):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except RuntimeError:
                pass

    def _publish(self, job_id: int, ev: dict) -> None:
        with self.lock:
            self._publish_locked(job_id, ev)

    def _work(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                self._run(job_id)
            except Exception as e:
                self.db.set_state(job_id, "failed", finished=time.time(), error=f"{type(e).__name__}: {e}")
                self._publish(
                    job_id,
                    {"event": "state", "state": "failed", "error": f"{type(e).__name__}: {e}"},
                )

    def _run(self, job_id: int) -> None:
        row = self.db.job(job_id)
        if row is None:
            return
        stop = threading.Event()
        with self.lock:
            if not self.db.claim(job_id):
                return
            self.stops[job_id] = stop
            self._publish_locked(job_id, {"event": "state", "state": "running"})

        def sink(ev: dict) -> None:
            if isinstance(ev.get("n"), int) and isinstance(ev.get("of"), int):
                self.db.progress(job_id, ev["n"], ev["of"])
            self._publish(job_id, {"event": "line", **ev})

        name = f"job-{job_id}"
        base = job.Job(settings={}, secrets={}, stop=stop, sink=sink, name=name)
        args = json.loads(row["args"])
        done = threading.Event()

        def renew() -> None:
            while not done.wait(LEASE_RENEW_S):
                try:
                    fleet.renew(self.cfg.fleet_url, name)
                except BooksmithError as e:
                    log(f"job {job_id}: lease not renewed: {e}", job=job_id)

        threading.Thread(target=renew, daemon=True).start()
        outcome: tuple[str, object] = ("failed", "not run")
        try:
            with base.active():
                result = os.path.relpath(dispatch(row["kind"], row["store"], args, base, self.db, self.cfg), row["store"])
                log(f"job {job_id} {row['kind']} done: {result}", job=job_id)
            outcome = ("done", result)
        except Cancelled:
            outcome = ("cancelled", None)
        except BooksmithError as e:
            outcome = ("failed", str(e))
        except Exception as e:
            outcome = ("failed", f"{type(e).__name__}: {e}")
        finally:
            done.set()
            if args.get("model"):
                try:
                    fleet.release(self.cfg.fleet_url, name)
                except BooksmithError as e:
                    log(f"job {job_id}: lease not released: {e}", job=job_id)
            with self.lock:
                self.stops.pop(job_id, None)
        state, payload = outcome
        if state == "done":
            self.db.set_state(job_id, "done", finished=time.time(), result=payload)
            self._publish(job_id, {"event": "state", "state": "done", "result": payload})
        elif state == "cancelled":
            self.db.set_state(job_id, "cancelled", finished=time.time())
            self._publish(job_id, {"event": "state", "state": "cancelled"})
        else:
            self.db.set_state(job_id, "failed", finished=time.time(), error=payload)
            self._publish(job_id, {"event": "state", "state": "failed", "error": payload})
