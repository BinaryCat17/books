import httpx

from backend.errors import Refusal, Unmeasurable


def _post(base: str, path: str, body: dict, timeout: float = 600.0) -> dict:
    try:
        r = httpx.post(base + path, json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise Unmeasurable(f"the metrics service did not answer: {e}") from None
    if r.status_code == 409:
        raise Refusal(r.json().get("error", r.text))
    if r.status_code == 422:
        raise Unmeasurable(r.json().get("error", r.text))
    if r.status_code != 200:
        raise Unmeasurable(f"the metrics service answered {r.status_code}: {r.text[:200]}")
    return r.json()


def measure(
    base: str,
    store: str,
    book: str,
    truth: str | None,
    kind: str,
    run: str,
    pages: list[int] | None = None,
    only: list[str] | None = None,
) -> list[dict]:
    return _post(
        base,
        "/measure",
        {"store": store, "book": book, "kind": kind, "run": run, "truth": truth, "pages": pages, "only": only},
    )["records"]


def pairs(base: str, store: str, book: str, kind: str, run: str, index: int, truth: str | None) -> dict:
    return _post(
        base,
        "/pairs",
        {"store": store, "book": book, "kind": kind, "run": run, "truth": truth, "index": index},
        timeout=120.0,
    )


def probe(base: str, store: str, book: str, kind: str, run: str, only: list[str] | None = None) -> dict:
    return _post(base, "/probe", {"store": store, "book": book, "kind": kind, "run": run, "only": only})
