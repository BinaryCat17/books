"""Jobs in the background: a queue, a few worker threads, one `Job` per job.

A worker enters a `Job` of its own with `active()` inside its thread, since
a thread inherits no context: the job's settings are the entry's, its
secrets the entry's, its stop the row's cancel, and its sink writes the
log's `n` and `of` into the row and hands every line to whoever listens.
The service is called with that job as `base`, and the run directory it
returns is the result. A crash before the row is closed is closed at the
next boot as failed, with the reason.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from collections.abc import AsyncIterator

from booksmith import service
from booksmith.core import job
from booksmith.core.errors import BooksmithError, Cancelled
from booksmith.core.log import log
from booksmith.web.db import TERMINAL, Db, as_dict

KINDS = ("detect", "hybrid", "read", "bench", "html")
KEEPALIVE_S = 15.0


def run_dir_of(store: str, book: str, kind: str, label: str) -> str:
    d = os.path.join(service.book_dir(store, book), kind, label)
    if not os.path.isdir(os.path.join(d, "pages")):
        raise BooksmithError(f"{book} has no {kind} run labelled {label!r}")
    return d


def dispatch(kind: str, store: str, args: dict, base: job.Job) -> str:
    """One kind of job to one service function, the caller's job handed in."""
    book = str(args.get("book") or "")
    model = str(args.get("model") or "")
    label = str(args.get("label") or "")
    pages = str(args.get("pages") or "") or None
    if kind == "detect":
        return service.detect(store, service.book_dir(store, book), {}, pages,
                              None, model, base=base)
    if kind == "hybrid":
        return service.hybrid(store, service.book_dir(store, book), {}, pages,
                              None, model, base=base)
    if kind == "read":
        return service.read(store, run_dir_of(store, book, "detect", label), {},
                            None, pages or "", "", model, base=base)
    if kind == "bench":
        return service.bench(store, service.book_dir(store, book), {}, run=label,
                             kind=str(args.get("run_kind") or "detect"), base=base)
    if kind == "html":
        return service.html(store, run_dir_of(store, book, str(args.get("run_kind") or "detect"),
                                              label), {}, None, base=base)
    raise BooksmithError(f"no such kind of job: {kind!r}; there are {KINDS}")


class Pool:
    """The workers over the queue. `reconcile` runs before the first worker:
    a row left running by a dead process is failed, never resumed blind."""

    def __init__(self, db: Db, workers: int = 2):
        self.db = db
        self.queue: queue.Queue[int] = queue.Queue()
        self.stops: dict[int, threading.Event] = {}
        # A listener is an asyncio queue and the loop it lives on: events are
        # published from worker threads, and a loop's queue is fed only from
        # its own thread, through the loop.
        self.listeners: dict[int, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict]]]] = {}
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []
        self.orphaned = db.orphans()
        for i in range(workers):
            t = threading.Thread(target=self._work, name=f"worker-{i}", daemon=True)
            t.start()
            self.threads.append(t)

    # --------------------------------------------------------- the door
    def submit(self, user_id: int, store: str, kind: str, args: dict) -> int:
        if kind not in KINDS:
            raise BooksmithError(f"no such kind of job: {kind!r}; there are {KINDS}")
        job_id = self.db.add_job(user_id, store, kind, str(args.get("book") or ""),
                                 str(args.get("label") or ""), str(args.get("model") or ""),
                                 args)
        self.queue.put(job_id)
        return job_id

    def cancel(self, job_id: int) -> bool:
        """A queued job is cancelled here; a running one is asked to stop and
        closes itself at its next check. Under the lock a worker takes to
        claim a job, so a cancel lands before the start or after it, never
        between the two."""
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
        """The row as it stands, then every line and state change until the
        job ends; a keepalive where nothing happened for a while. Async, so a
        thousand open streams hold no thread each."""
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
                except asyncio.TimeoutError:
                    yield {"event": "keepalive"}
                    continue
                yield ev
                if ev.get("event") == "state" and ev.get("state") in TERMINAL:
                    return
        finally:
            with self.lock:
                self.listeners[job_id] = [
                    (lp, qq) for lp, qq in self.listeners.get(job_id, []) if qq is not q]

    # ------------------------------------------------------- the workers
    def _publish_locked(self, job_id: int, ev: dict) -> None:
        for loop, q in self.listeners.get(job_id, []):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except RuntimeError:
                pass                     # the loop is closed: nobody listens

    def _publish(self, job_id: int, ev: dict) -> None:
        with self.lock:
            self._publish_locked(job_id, ev)

    def _work(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                self._run(job_id)
            except Exception as e:  # said on the row, never lost in a thread
                self.db.set_state(job_id, "failed", finished=time.time(),
                                  error=f"{type(e).__name__}: {e}")
                self._publish(job_id, {"event": "state", "state": "failed",
                                       "error": f"{type(e).__name__}: {e}"})

    def _run(self, job_id: int) -> None:
        row = self.db.job(job_id)
        if row is None:
            return
        stop = threading.Event()
        # Claimed under the lock a cancel takes: queued to running in one
        # step, and a row a cancel closed first is not run at all.
        with self.lock:
            if not self.db.claim(job_id):
                return
            self.stops[job_id] = stop
            self._publish_locked(job_id, {"event": "state", "state": "running"})

        def sink(ev: dict) -> None:
            if isinstance(ev.get("n"), int) and isinstance(ev.get("of"), int):
                self.db.progress(job_id, ev["n"], ev["of"])
            self._publish(job_id, {"event": "line", **ev})

        base = job.Job(settings={}, secrets={}, stop=stop, sink=sink)
        args = json.loads(row["args"])
        try:
            with base.active():
                result = os.path.relpath(dispatch(row["kind"], row["store"], args, base),
                                         row["store"])
                log(f"job {job_id} {row['kind']} done: {result}", job=job_id)
        except Cancelled:
            self.db.set_state(job_id, "cancelled", finished=time.time())
            self._publish(job_id, {"event": "state", "state": "cancelled"})
        except BooksmithError as e:
            self.db.set_state(job_id, "failed", finished=time.time(), error=str(e))
            self._publish(job_id, {"event": "state", "state": "failed", "error": str(e)})
        except Exception as e:
            why = f"{type(e).__name__}: {e}"
            self.db.set_state(job_id, "failed", finished=time.time(), error=why)
            self._publish(job_id, {"event": "state", "state": "failed", "error": why})
        else:
            self.db.set_state(job_id, "done", finished=time.time(), result=result)
            self._publish(job_id, {"event": "state", "state": "done", "result": result})
        finally:
            with self.lock:
                self.stops.pop(job_id, None)
