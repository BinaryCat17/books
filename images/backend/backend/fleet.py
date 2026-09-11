import httpx

from backend.errors import Refusal


def _call(method: str, url: str, body: dict | None = None, timeout: float = 30.0) -> dict | list:
    try:
        r = httpx.request(method, url, json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise Refusal(f"the fleet did not answer: {e}") from None
    if r.status_code == 409:
        raise Refusal(r.json().get("error", r.text))
    if r.status_code != 200:
        raise Refusal(f"the fleet answered {r.status_code}: {r.text[:200]}")
    return r.json()


def models(base: str) -> dict:
    return _call("GET", base + "/models")


def write_models(base: str, raw: dict) -> dict:
    return _call("PUT", base + "/models", raw)


def lease(base: str, model: str, job: str) -> dict:
    return _call("POST", base + "/leases", {"model": model, "job": job}, timeout=1200.0)


def renew(base: str, job: str) -> int:
    return int(_call("POST", base + "/leases/renew", {"job": job})["renewed"])


def release(base: str, job: str) -> int:
    return int(_call("POST", base + "/leases/release", {"job": job})["released"])
