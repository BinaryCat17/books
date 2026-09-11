import hashlib
import json
import os
import shutil
import threading
import time

import jsonschema

from backend import classes as policy
from backend import schema
from backend.errors import Refusal
from backend.page import parse_anchor, write_json

SUFFIX = ".corrected"
_LOCK = threading.Lock()


def base_of(run_dir: str) -> str:
    run_dir = run_dir.rstrip("/")
    return run_dir[: -len(SUFFIX)] if run_dir.endswith(SUFFIX) else run_dir


def derived_of(base_dir: str) -> str:
    return base_dir.rstrip("/") + SUFFIX


def _snapshot(run_dir: str) -> dict:
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)


def listed(base_dir: str) -> list[dict]:
    d = derived_of(base_dir)
    return list(_snapshot(d).get("corrections") or []) if os.path.isdir(d) else []


def check(c: dict, base_dir: str, pol: policy.Policy) -> None:
    try:
        schema.validate(c, "correction.schema.json")
    except jsonschema.ValidationError as e:
        raise Refusal(f"not a correction: {e.message}") from None
    try:
        index, block_id = parse_anchor(c["anchor"])
    except ValueError as e:
        raise Refusal(str(e)) from None
    path = os.path.join(base_dir, "pages", f"{index:04d}.json")
    if block_id is None or not os.path.isfile(path):
        raise Refusal(f"no block {c['anchor']} in the run")
    with open(path, encoding="utf-8") as f:
        if not any(b["block_id"] == block_id for b in json.load(f)["blocks"]):
            raise Refusal(f"no block {c['anchor']} in the run")
    if "label" in c and c["label"] not in pol.classes:
        raise Refusal(f"{c['label']!r} is not in the run's vocabulary: {', '.join(sorted(pol.classes))}")


def _own(out: str, base_dir: str) -> None:
    snap = os.path.join(out, "run.json")
    if not os.path.exists(snap):
        return
    try:
        who = (_snapshot(out).get("derived_from") or {}).get("label")
    except (OSError, ValueError):
        who = None
    if who != os.path.basename(base_dir):
        raise Refusal(f"{os.path.basename(out)} is a run of its own, not derived from {os.path.basename(base_dir)}; it is not rewritten")


def identity_of(base_identity: str | None, corrections: list[dict]) -> str:
    said = [{k: v for k, v in c.items() if k in ("anchor", "content", "label", "drop")} for c in corrections]
    blob = json.dumps({"base": base_identity, "corrections": said}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _apply(page: dict, fixes: list[dict]) -> dict:
    blocks = []
    for b in page["blocks"]:
        mine = [c for c in fixes if c["block_id"] == b["block_id"]]
        if any(c.get("drop") for c in mine):
            continue
        for c in mine:
            if "label" in c:
                b = {**b, "label": c["label"]}
            if "content" in c:
                b = {**b, "content": c["content"], "kind": "text" if c["content"] else "none"}
        blocks.append(b)
    return {**page, "blocks": blocks}


def derive(base_dir: str, corrections: list[dict]) -> str:
    base_dir = base_dir.rstrip("/")
    out = derived_of(base_dir)
    _own(out, base_dir)
    snap = _snapshot(base_dir)
    pol = policy.Policy.from_snapshot(snap.get("policy"))
    dropped = set()
    for c in corrections:
        check(c, base_dir, pol)
        if c["anchor"] in dropped:
            raise Refusal(f"{c['anchor']} was dropped by an earlier correction; undo that first")
        if c.get("drop"):
            dropped.add(c["anchor"])
    by_page: dict[int, list[dict]] = {}
    touched: dict[str, dict] = {}
    for c in corrections:
        index, block_id = parse_anchor(c["anchor"])
        by_page.setdefault(index, []).append({**c, "block_id": block_id})
        if "content" in c or c.get("drop"):
            touched[c["anchor"]] = {"author": c.get("author"), "when": c.get("when")}
    tmp = out + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "pages"))
    pages_dir = os.path.join(base_dir, "pages")
    for name in sorted(os.listdir(pages_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(pages_dir, name), encoding="utf-8") as f:
            page = json.load(f)
        write_json(os.path.join(tmp, "pages", name), _apply(page, by_page.get(int(page["index"]), [])), indent=1)
    answers = os.path.join(base_dir, "answers")
    if os.path.isdir(answers):
        os.makedirs(os.path.join(tmp, "answers"))
        for name in sorted(os.listdir(answers)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(answers, name), encoding="utf-8") as f:
                d = json.load(f)
            d["answers"] = [
                {**a, "corrected": touched[a["anchor"]]} if a.get("anchor") in touched else a for a in (d.get("answers") or [])
            ]
            write_json(os.path.join(tmp, "answers", name), d, indent=1)
    if os.path.isdir(os.path.join(base_dir, "crops")):
        os.symlink(os.path.join("..", os.path.basename(base_dir), "crops"), os.path.join(tmp, "crops"))
    write_json(
        os.path.join(tmp, "run.json"),
        {
            **snap,
            "label": os.path.basename(out),
            "identity": identity_of(snap.get("identity"), corrections),
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "derived_from": {
                "kind": os.path.basename(os.path.dirname(base_dir)),
                "label": os.path.basename(base_dir),
                "identity": snap.get("identity"),
                "when": snap.get("when"),
            },
            "corrections": corrections,
        },
        indent=1,
    )
    old = out + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out):
        os.rename(out, old)
    os.rename(tmp, out)
    shutil.rmtree(old, ignore_errors=True)
    return out


def add(base_dir: str, c: dict, author: str) -> str:
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOCK:
        return derive(base_dir, listed(base_dir) + [{**c, "author": author, "when": when}])


def remove(base_dir: str, n: int) -> str | None:
    with _LOCK:
        have = listed(base_dir)
        if not 0 <= n < len(have):
            raise Refusal(f"no correction {n}; there are {len(have)}")
        kept = have[:n] + have[n + 1 :]
        if kept:
            return derive(base_dir, kept)
        _own(derived_of(base_dir), base_dir)
        shutil.rmtree(derived_of(base_dir), ignore_errors=True)
        return None


def again(base_dir: str) -> str:
    with _LOCK:
        have = listed(base_dir)
        if not have:
            raise Refusal(f"{os.path.basename(base_dir)} has no corrections to derive from")
        return derive(base_dir, have)


def stale(derived_dir: str) -> bool:
    snap = _snapshot(derived_dir)
    who = snap.get("derived_from") or {}
    base = os.path.join(os.path.dirname(derived_dir), who.get("label") or "")
    if not who or not os.path.isfile(os.path.join(base, "run.json")):
        return True
    now = _snapshot(base)
    return (now.get("identity"), now.get("when")) != (who.get("identity"), who.get("when"))
