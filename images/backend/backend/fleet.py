import httpx

from backend import settings
from backend.errors import Refusal


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30.0) -> dict | list:
    cfg = settings.Settings.from_env()
    headers = {"Authorization": f"Bearer {cfg.fleet_key}"} if cfg.fleet_key else {}
    try:
        r = httpx.request(method, cfg.fleet_url + path, json=body, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise Refusal(f"the fleet did not answer: {e}") from None
    if r.status_code == 409:
        raise Refusal(r.json().get("error", r.text))
    if r.status_code not in (200, 202):
        raise Refusal(f"the fleet answered {r.status_code}: {r.text[:200]}")
    return r.json()


def models() -> dict:
    return _call("GET", "/models")


def write_models(raw: dict) -> dict:
    return _call("PUT", "/models", raw)


def lease(model: str, job: str, wait_s: float = 60.0) -> dict:
    return _call("POST", "/leases", {"model": model, "job": job, "wait_s": wait_s}, timeout=wait_s + 30.0)


def renew(job: str) -> int:
    return int(_call("POST", "/leases/renew", {"job": job})["renewed"])


def release(job: str) -> int:
    return int(_call("POST", "/leases/release", {"job": job})["released"])


def placements() -> list:
    return _call("GET", "/placements")


def ledger() -> list:
    return _call("GET", "/ledger")


def stop_placement(pid: str) -> dict:
    return _call("DELETE", f"/placements/{pid}")
