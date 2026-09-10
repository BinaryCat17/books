"""The job: what a run reads, whether it may go on, and where its lines go.

One object on a context variable. `knobs.knob` reads its settings, `log`
writes to its sink, and a loop asks `check` before the next page. The default
job is the process itself: settings are the knobs set in the environment,
seen live, and the sink prints. A job refuses to become current with a
setting no knob is declared for, so a value that reaches nothing cannot ride
in silently.
"""
import contextvars
import os
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

from booksmith.core.errors import Cancelled, Refusal


def _print(event: dict) -> None:
    """The default sink: the text with a timestamp, to stdout, flushed.

    Stdout and not stderr: the acceptance snapshots are the concatenation of
    both streams compared line by line, and a diagnostic on stderr would
    reorder every report.
    """
    print(f"[{time.strftime('%H:%M:%S')}]", event["text"], flush=True)


class _Environ(Mapping):
    """The knobs set in the process environment, seen live: a test that sets
    one after the default job was made must see it. The registry is imported
    at each call because `knobs` imports this module."""
    @staticmethod
    def _names() -> tuple[str, ...]:
        from booksmith.core import knobs
        return knobs.names()

    def __getitem__(self, name: str) -> str:
        if name in self._names():
            return os.environ[name]
        raise KeyError(name)

    def __iter__(self) -> Iterator[str]:
        return (n for n in self._names() if n in os.environ)

    def __len__(self) -> int:
        return sum(1 for _ in self)


@dataclass
class Job:
    settings: Mapping = field(default_factory=_Environ)
    stop: threading.Event = field(default_factory=threading.Event)
    sink: Callable[[dict], None] = _print

    def check(self) -> None:
        if self.stop.is_set():
            raise Cancelled("the job was stopped")

    @contextmanager
    def active(self) -> Iterator["Job"]:
        from booksmith.core import knobs
        bad = sorted(set(self.settings) - set(knobs.names()))
        if bad:
            raise Refusal(f"settings for knobs nothing declares: {bad}")
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)


_DEFAULT = Job()
_current: contextvars.ContextVar = contextvars.ContextVar("job")


def current() -> Job:
    return _current.get(_DEFAULT)


def spawn(fn: Callable, *args: object) -> threading.Thread:
    """A daemon thread that sees the current job: a thread inherits no context
    variable on its own, and its lines would fall to the default sink."""
    ctx = contextvars.copy_context()
    t = threading.Thread(target=ctx.run, args=(fn, *args), daemon=True)
    t.start()
    return t
