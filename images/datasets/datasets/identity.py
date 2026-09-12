from collections.abc import Iterable, Mapping
import hashlib
import json
import os


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def commit() -> str | None:
    return os.environ.get("BOOKSMITH_COMMIT") or None


FINGERPRINT_NOT_IDENTITY = {
    "weights_dir": "a machine-local path; the weights themselves are in sha256_weights, which IS the experiment",
    "summary": "run-born: docling writes its pipeline totals into the fingerprint AFTER the pages, so it exists only once the run is over -- and it is NESTED, under `docling_pipeline`, which is why the exclusion goes to every depth",
    "dir": "a machine-local path to the weights, wherever it appears. The reading adapter's `weights` block opens with `VL_MODEL_DIR`, so excluding that knob and admitting the same fact one field over was no exclusion at all: two readings of one book on two rented cards got two identities",
    "file_count": "how many files that directory happened to hold; it moves with the download, not with the model",
}
KNOBS_NOT_IDENTITY = {
    "VLM_ENDPOINT": "the rented machine's address, new on every rental",
    "LAYOUT_ENDPOINT": "where a served layout model was reached; the model itself is in the fingerprint",
    "LAYOUT_ADAPTER": "how the model was reached, in-process or served; what answered is the fingerprint's name and weights, so a served run of a model is the run of that model",
    "LAYOUT_MODEL_DIR": "a machine-local path to the weights",
    "VL_MODEL_DIR": "a machine-local path to the weights",
    "BOOKSMITH_LEDGER": "where the run journal is written",
    "BOOKSMITH_COMMIT": "how the commit is discovered on a box without git",
}


def _without(obj: object, names: Iterable[str]) -> object:
    if isinstance(obj, dict):
        return {k: _without(v, names) for k, v in obj.items() if k not in names}
    if isinstance(obj, list):
        return [_without(v, names) for v in obj]
    return obj


def identity(fingerprint: dict, knob_values: dict) -> str:
    keep_f = _without(fingerprint or {}, FINGERPRINT_NOT_IDENTITY)
    keep_k = {k: v for k, v in (knob_values or {}).items() if k not in KNOBS_NOT_IDENTITY}
    blob = json.dumps(
        {"fingerprint": keep_f, "knobs": keep_k}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def merge_knobs(server: Mapping, client: Mapping) -> dict:
    both = {
        k: (server[k], client[k])
        for k in server
        if k in client and k not in KNOBS_NOT_IDENTITY and (str(server[k]) != str(client[k]))
    }
    if both:
        from datasets.errors import Refusal

        raise Refusal(
            f"knobs read on both sides of the model with two values: { {k: list(v) for k, v in both.items()} }. One run cannot be two experiments; set the value on one side only."
        )
    return {**(server or {}), **(client or {})}


def knob_values(snapshot: dict) -> dict:
    out = {}
    for name, entry in ((snapshot or {}).get("knobs") or {}).items():
        if not isinstance(entry, dict):
            out[name] = entry
        elif entry.get("for_this_run"):
            out[name] = entry.get("value")
    spoken = (snapshot or {}).get("served")
    if isinstance(spoken, dict) and isinstance(spoken.get("knobs"), dict):
        out = merge_knobs(spoken["knobs"], out)
    return out
