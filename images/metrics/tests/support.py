from contextlib import contextmanager

from metrics import job


@contextmanager
def said():
    lines = []
    with job.Job(sink=lambda e: lines.append(e["text"])).active():
        yield lines
