"""The job: what a run reads, whether it may go on, and where its lines go"""

import contextvars
import os
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from metrics.errors import Cancelled, Refusal


def _print(event: dict) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", event["text"], flush=True)


class _Environ(Mapping):
    @staticmethod
    def _names() -> tuple[str, ...]:
        from metrics import knobs

        return knobs.names()

    def __getitem__(self, name: str) -> str:
        if name in self._names():
            return os.environ[name]
        raise KeyError(name)

    def __iter__(self) -> Iterator[str]:
        return (n for n in self._names() if n in os.environ)

    def __len__(self) -> int:
        return sum((1 for _ in self))


@dataclass
class Job:
    settings: Mapping = field(default_factory=_Environ)
    secrets: Mapping = field(default_factory=dict)
    stop: threading.Event = field(default_factory=threading.Event)
    sink: Callable[[dict], None] = _print

    def check(self) -> None:
        if self.stop.is_set():
            raise Cancelled("the job was stopped")

    @contextmanager
    def active(self) -> Iterator["Job"]:
        from metrics import knobs

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
    ctx = contextvars.copy_context()
    t = threading.Thread(target=ctx.run, args=(fn, *args), daemon=True)
    t.start()
    return t
