"""What both shims stand on: a threading server whose request threads see
the job the service was built under, a key comparison that leaks no timing,
and a wait that a signal ends.

A new thread inherits no context variable, and `knobs.knob` reads the job
on one: without this every request would read the process's default job,
and the describe's knob values would name settings that did not decide the
answers. A service copies the context it was built under, the one its
describe was taken in; the server runs each request under a copy of that,
since a copied context may not be entered twice at once.
"""
from __future__ import annotations

import contextvars
import hmac
import threading
from http.server import ThreadingHTTPServer

from booksmith.core import job
from booksmith.core.log import log


class Server(ThreadingHTTPServer):
    """A request thread runs under the context the service was built in."""

    def __init__(self, address: tuple[str, int], handler: type,
                 context: contextvars.Context) -> None:
        super().__init__(address, handler)
        self.context = context

    def process_request_thread(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        self.context.copy().run(super().process_request_thread, request, client_address)


def key_ok(header: str | None, key: str | None) -> bool:
    """Whether a bearer header carries the key; no key set means no door."""
    if not key:
        return True
    want = "Bearer " + key
    return header is not None and hmac.compare_digest(header, want)


def run_until_stopped(srv: ThreadingHTTPServer, what: str) -> None:
    """Serve until the job is stopped -- a signal, under the command line --
    then shut the server down and say how it ended. The wait is on the job's
    stop and not on `serve_forever`, which a signal cannot end."""
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        job.current().stop.wait()
    except KeyboardInterrupt:
        pass
    log(f"{what}: stopping")
    srv.shutdown()
    srv.server_close()
