import json
import os
import secrets
import threading
import time

import httpx

from fleet import registry, settings
from fleet.errors import Refusal
from fleet.files import write_json
from fleet.log import log

TTL_S = 120.0
BOOT_S = 900.0
POLL_S = 3.0
RECONCILE_EVERY = 10


def probe(endpoint: str, key: str, timeout: float = 5.0) -> bool:
    try:
        r = httpx.get(endpoint + "/booksmith/health", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        return r.status_code == 200 and bool(r.json().get("ready"))
    except (httpx.HTTPError, ValueError):
        return False


class Fleet:
    def __init__(self, providers: dict, clock=time.time, probe=probe, boot_s: float = BOOT_S, poll_s: float = POLL_S):
        self.providers, self.clock, self.probe, self.boot_s, self.poll_s = providers, clock, probe, boot_s, poll_s
        self.path = os.path.join(settings.home(), "fleet", "placements.json")
        self.ledger_path = os.path.join(settings.home(), "fleet", "ledger.jsonl")
        self.lock = threading.RLock()
        self.table = {"placements": {}, "leases": {}}
        self.sweeps = 0
        if os.path.isfile(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.table = json.load(f)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        write_json(self.path, self.table, indent=1)

    def placements(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self.table["placements"].values()]

    def leases(self) -> list[dict]:
        with self.lock:
            return [dict(v) for v in self.table["leases"].values()]

    def ensure(self, model: str, job: str, wait_s: float | None = None) -> dict:
        entry = registry.load().get(model)
        if entry is None:
            raise Refusal(f"no model {model!r} in the registry")
        if entry.get("endpoint"):
            return {"state": "ready", "endpoint": entry["endpoint"], "key": entry.get("api_key") or "", "lease": None, "placement": None}
        creating = False
        with self.lock:
            for lid, lease in self.table["leases"].items():
                p = self.table["placements"].get(lease["placement"])
                if lease["job"] == job and p and p["state"] == "ready":
                    lease["expires"] = self.clock() + TTL_S
                    self._save()
                    return {"state": "ready", "endpoint": p["endpoint"], "key": p["key"], "lease": lid, "placement": p["id"]}
            p = next((p for p in self.table["placements"].values()
                      if p["model"] == model and p["state"] in ("ready", "starting", "creating")), None)
            if p is None:
                provider = self.providers.get(entry["provider"])
                if provider is None:
                    raise Refusal(f"{model}: provider {entry['provider']!r} is not available here")
                now = self.clock()
                p = {"id": secrets.token_hex(6), "model": model, "provider": provider.name, "handle": None,
                     "endpoint": "", "key": secrets.token_hex(16), "state": "creating", "started": now,
                     "ready_at": None, "last_used": now, "rate_usd_h": 0.0, "budget_usd": entry["budget_usd"],
                     "idle_s": entry["idle_s"], "port": entry["port"], "deadline": None, "why": None}
                self.table["placements"][p["id"]] = p
                self._save()
                creating = True
            pid, key = p["id"], p["key"]
        if creating:
            self._create(pid, model, entry, key)
        until = None if wait_s is None else self.clock() + wait_s
        if not self._wait_ready(pid, until):
            return {"state": "starting", "endpoint": "", "key": "", "lease": None, "placement": pid}
        with self.lock:
            p = self.table["placements"][pid]
            lid = secrets.token_hex(8)
            self.table["leases"][lid] = {"id": lid, "placement": pid, "job": job, "expires": self.clock() + TTL_S}
            p["last_used"] = self.clock()
            self._save()
            return {"state": "ready", "endpoint": p["endpoint"], "key": p["key"], "lease": lid, "placement": pid}

    def _create(self, pid: str, model: str, entry: dict, key: str) -> None:
        provider = self.providers[entry["provider"]]
        try:
            handle = provider.start(model, entry, key)
        except Exception:
            with self.lock:
                self.table["placements"].pop(pid, None)
                self._save()
            raise
        with self.lock:
            p = self.table["placements"].get(pid)
            if p is None:
                provider.stop(handle["id"])
                raise Refusal(f"{model}: the placement was stopped while starting")
            now = self.clock()
            rate = float(handle.get("rate_usd_h") or 0.0)
            p.update({"handle": handle["id"], "endpoint": handle.get("endpoint") or "", "rate_usd_h": rate,
                      "state": "starting", "started": now,
                      "deadline": (now + p["budget_usd"] / rate * 3600.0) if rate > 0 and p["budget_usd"] > 0 else None})
            self._save()
        log(f"{model}: placement {pid} starting on {provider.name} ({handle['id']})")

    def _wait_ready(self, pid: str, until: float | None = None) -> bool:
        while True:
            with self.lock:
                p = dict(self.table["placements"].get(pid) or {})
            if not p:
                raise Refusal("the placement was stopped while starting")
            if p["state"] == "ready":
                return True
            if p["state"] in ("creating", "stopping"):
                if until is not None and self.clock() >= until:
                    return False
                time.sleep(self.poll_s)
                continue
            provider = self.providers.get(p["provider"])
            if provider is None:
                raise Refusal(f"{p['model']}: provider {p['provider']!r} is not available here")
            endpoint, died = p["endpoint"], None
            if not endpoint and hasattr(provider, "endpoint"):
                try:
                    endpoint = provider.endpoint(p["handle"], p["port"])
                except Refusal as e:
                    died = str(e)
            ok = bool(endpoint) and died is None and self.probe(endpoint, p["key"])
            alive = True if ok or died else provider.alive(p["handle"])
            with self.lock:
                q = self.table["placements"].get(pid)
                if q is None:
                    raise Refusal("the placement was stopped while starting")
                if endpoint and not q["endpoint"]:
                    q["endpoint"] = endpoint
                if ok:
                    q["state"], q["ready_at"] = "ready", self.clock()
                    self._save()
                    log(f"{q['model']}: placement {pid} ready at {q['endpoint']}")
                    return True
                if q["state"] == "stopping":
                    raise Refusal(f"{p['model']}: stopped while starting")
                why = ("died while starting" if died or not alive
                       else "boot deadline" if self.clock() - q["started"] > self.boot_s else None)
                self._save()
            if why:
                self._stop(pid, why)
                raise Refusal(f"{p['model']}: {why}" + (f": {died}" if died else ""))
            if until is not None and self.clock() >= until:
                return False
            time.sleep(self.poll_s)

    def renew(self, job: str) -> int:
        with self.lock:
            n = 0
            for lease in self.table["leases"].values():
                if lease["job"] == job:
                    lease["expires"] = self.clock() + TTL_S
                    p = self.table["placements"].get(lease["placement"])
                    if p:
                        p["last_used"] = self.clock()
                    n += 1
            self._save()
            return n

    def release(self, job: str) -> int:
        with self.lock:
            gone = [lid for lid, lease in self.table["leases"].items() if lease["job"] == job]
            for lid in gone:
                p = self.table["placements"].get(self.table["leases"][lid]["placement"])
                if p:
                    p["last_used"] = self.clock()
                del self.table["leases"][lid]
            self._save()
            return len(gone)

    def sweep(self) -> list[str]:
        with self.lock:
            now = self.clock()
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["expires"] < now]:
                p = self.table["placements"].get(self.table["leases"][lid]["placement"])
                if p:
                    p["last_used"] = max(p["last_used"], self.table["leases"][lid]["expires"])
                del self.table["leases"][lid]
            live = {lease["placement"] for lease in self.table["leases"].values()}
            todo, ready = [], []
            for pid, p in self.table["placements"].items():
                if p["handle"] is None:
                    continue
                if p["state"] == "stopping":
                    todo.append((pid, p.get("why") or "stopping"))
                elif p["deadline"] is not None and now >= p["deadline"]:
                    todo.append((pid, "budget"))
                elif p["state"] == "ready" and pid not in live and now - p["last_used"] > p["idle_s"]:
                    todo.append((pid, "idle"))
                elif p["state"] == "starting" and now - p["started"] > self.boot_s:
                    todo.append((pid, "boot deadline"))
                elif p["state"] == "ready":
                    ready.append((pid, p["provider"], p["handle"]))
            self._save()
        stopped = [pid for pid, why in todo if self._stop(pid, why)]
        for pid, name, handle in ready:
            provider = self.providers.get(name)
            if provider is not None and not provider.alive(handle) and self._stop(pid, "died"):
                stopped.append(pid)
        self.sweeps += 1
        if self.sweeps % RECONCILE_EVERY == 0:
            self.reconcile()
        return stopped

    def reconcile(self) -> dict:
        out = {"adopted": 0, "destroyed": 0, "gone": 0}
        for name, provider in self.providers.items():
            try:
                found = provider.list()
            except Exception as e:
                log(f"reconcile: {name} did not answer: {e}")
                continue
            with self.lock:
                known = {p["handle"]: pid for pid, p in self.table["placements"].items()
                         if p["provider"] == name and p["handle"] is not None}
            listed = {h["id"] for h in found}
            for h in found:
                if h["id"] in known:
                    if h.get("state") and h["state"] not in ("running", "starting", "created", "loading"):
                        self._forget(known[h["id"]], "gone")
                        out["gone"] += 1
                    else:
                        out["adopted"] += 1
                else:
                    log(f"reconcile: destroying {name} {h['id']} ({h.get('model')}): not in the table")
                    provider.stop(h["id"])
                    out["destroyed"] += 1
            for handle, pid in known.items():
                if handle not in listed and not provider.alive(handle):
                    self._forget(pid, "gone")
                    out["gone"] += 1
        with self.lock:
            live = set(self.table["placements"])
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["placement"] not in live]:
                del self.table["leases"][lid]
            self._save()
        return out

    def stop(self, pid: str, why: str = "asked") -> None:
        with self.lock:
            if pid not in self.table["placements"]:
                raise Refusal(f"no placement {pid}")
        if not self._stop(pid, why):
            raise Refusal(f"placement {pid} could not be stopped; it is marked stopping and will be retried")

    def _stop(self, pid: str, why: str) -> bool:
        with self.lock:
            p = self.table["placements"].get(pid)
            if p is None:
                return False
            p["state"], p["why"] = "stopping", why
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["placement"] == pid]:
                del self.table["leases"][lid]
            self._save()
            provider, handle, model = self.providers.get(p["provider"]), p["handle"], p["model"]
        try:
            if handle is not None:
                if provider is None:
                    raise Refusal(f"provider {p['provider']!r} is not available here")
                provider.stop(handle)
        except Exception as e:
            log(f"{model}: placement {pid} NOT stopped ({why}): {e}; kept as stopping, retried at the next sweep")
            return False
        self._forget(pid, why)
        log(f"{model}: placement {pid} stopped: {why}")
        return True

    def _forget(self, pid: str, why: str) -> None:
        with self.lock:
            p = self.table["placements"].pop(pid, None)
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["placement"] == pid]:
                del self.table["leases"][lid]
            if p is not None and p["handle"] is not None:
                self._ledger(p, why)
            self._save()

    def _ledger(self, p: dict, why: str) -> None:
        now = self.clock()
        row = {"model": p["model"], "provider": p["provider"], "handle": p["handle"], "started": p["started"],
               "stopped": now, "rate_usd_h": p["rate_usd_h"],
               "cost_usd": round(p["rate_usd_h"] * (now - p["started"]) / 3600.0, 4), "why": why}
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def ledger(self) -> list[dict]:
        if not os.path.isfile(self.ledger_path):
            return []
        with open(self.ledger_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
