import os
from contextlib import contextmanager

from datasets import job


@contextmanager
def said():
    lines = []
    with job.Job(sink=lambda e: lines.append(e["text"])).active():
        yield lines


@contextmanager
def env(**kw):
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
