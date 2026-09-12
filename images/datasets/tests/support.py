import json
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


def load_pages(d: str, what: str = "pages") -> dict:
    if not os.path.isdir(d):
        raise AssertionError(f"{what}: no directory {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name in ("run.json", "manifest.json"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if not (isinstance(p, dict) and "blocks" in p and ("index" in p)):
            raise AssertionError(f"{what}: {name} in {d} does not look like a markup page (no blocks/index)")
        out[int(p["index"])] = p
    if not out:
        raise AssertionError(f"{what}: no markup pages in {d}")
    return out
