"""Shared by the checks: where the sources are, and a knob set for one block."""
import os
from contextlib import contextmanager

# The source directory, from here rather than from cwd.
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "src", "booksmith")

# The key by which an adapter tells the metric whose order it returned.
ORDER_KEY = "reading_order"


def src_path(rel: str) -> str:
    p = os.path.join(SRC, rel)
    if not os.path.isfile(p):
        raise AssertionError(f"no source {rel} (looked in {SRC})")
    return p


@contextmanager
def env(**kw):
    """Set knobs for one block and restore them after, so no check poisons the next."""
    was = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
