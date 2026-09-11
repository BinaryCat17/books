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


def probe(endpoint: str, key: str, timeout: float = 5.0) -> bool:
    try:
        r = httpx.get(endpoint + "/booksmith/health", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        return r.status_code == 200 and bool(r.json().get("ready"))
    except (httpx.HTTPError, ValueError):
        return False


class Fleet:
    def __init__(self, providers: dict, clock=time.time, probe=probe, boot_s: float = BOOT_S):
        self.providers, self.clock, self.probe, self.boot_s = providers, clock, probe, boot_s
        self.path = os.path.join(settings.home(), "fleet", "placements.json")
        self.ledger_path = os.path.join(settings.home(), "fleet", "ledger.jsonl")
        self.lock = threading.RLock()
        self.table = {"placements": {}, "leases": {}}
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

    def ensure(self, model: str, job: str) -> dict:
        entry = registry.load().get(model)
        if entry is None:
            raise Refusal(f"no model {model!r} in the registry")
        if entry.get("endpoint"):
            return {"endpoint": entry["endpoint"], "key": entry.get("api_key") or "", "lease": None, "placement": None}
        with self.lock:
            for lid, lease in self.table["leases"].items():
                p = self.table["placements"].get(lease["placement"])
                if lease["job"] == job and p and p["state"] == "ready":
                    lease["expires"] = self.clock() + TTL_S
                    self._save()
                    return {"endpoint": p["endpoint"], "key": p["key"], "lease": lid, "placement": p["id"]}
            p = next((p for p in self.table["placements"].values() if p["model"] == model and p["state"] in ("ready", "starting")), None)
            if p is None:
                p = self._start(model, entry)
        self._wait_ready(p["id"])
        with self.lock:
            p = self.table["placements"][p["id"]]
            lid = secrets.token_hex(8)
            self.table["leases"][lid] = {"id": lid, "placement": p["id"], "job": job, "expires": self.clock() + TTL_S}
            p["last_used"] = self.clock()
            self._save()
            return {"endpoint": p["endpoint"], "key": p["key"], "lease": lid, "placement": p["id"]}

    def _start(self, model: str, entry: dict) -> dict:
        provider = self.providers.get(entry["provider"])
        if provider is None:
            raise Refusal(f"{model}: provider {entry['provider']!r} is not available here")
        key = secrets.token_hex(16)
        handle = provider.start(model, entry, key)
        now = self.clock()
        rate = float(handle.get("rate_usd_h") or 0.0)
        p = {"id": secrets.token_hex(6), "model": model, "provider": provider.name, "handle": handle["id"],
             "endpoint": handle.get("endpoint") or "", "key": key, "state": "starting", "started": now,
             "ready_at": None, "last_used": now, "rate_usd_h": rate, "budget_usd": entry["budget_usd"],
             "idle_s": entry["idle_s"], "port": entry["port"],
             "deadline": (now + entry["budget_usd"] / rate * 3600.0) if rate > 0 and entry["budget_usd"] > 0 else None}
        self.table["placements"][p["id"]] = p
        self._save()
        log(f"{model}: placement {p['id']} starting on {provider.name} ({handle['id']})")
        return p

    def _wait_ready(self, pid: str) -> None:
        while True:
            with self.lock:
                p = self.table["placements"].get(pid)
                if p is None:
                    raise Refusal("the placement was stopped while starting")
                if p["state"] == "ready":
                    return
                provider = self.providers[p["provider"]]
                if not p["endpoint"] and hasattr(provider, "endpoint"):
                    p["endpoint"] = provider.endpoint(p["handle"], p["port"])
                if p["endpoint"] and self.probe(p["endpoint"], p["key"]):
                    p["state"], p["ready_at"] = "ready", self.clock()
                    self._save()
                    log(f"{p['model']}: placement {pid} ready at {p['endpoint']}")
                    return
                if not provider.alive(p["handle"]):
                    self._stop(pid, "died while starting")
                    raise Refusal(f"{p['model']}: the placement died while starting")
                if self.clock() - p["started"] > self.boot_s:
                    self._stop(pid, "boot deadline")
                    raise Refusal(f"{p['model']}: not ready within {self.boot_s:.0f} s")
            time.sleep(1.0)

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
        stopped = []
        with self.lock:
            now = self.clock()
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["expires"] < now]:
                p = self.table["placements"].get(self.table["leases"][lid]["placement"])
                if p:
                    p["last_used"] = max(p["last_used"], self.table["leases"][lid]["expires"])
                del self.table["leases"][lid]
            live = {lease["placement"] for lease in self.table["leases"].values()}
            for pid, p in list(self.table["placements"].items()):
                if p["deadline"] is not None and now >= p["deadline"]:
                    self._stop(pid, "budget")
                    stopped.append(pid)
                elif p["state"] == "ready" and pid not in live and now - p["last_used"] > p["idle_s"]:
                    self._stop(pid, "idle")
                    stopped.append(pid)
                elif p["state"] == "starting" and now - p["started"] > self.boot_s:
                    self._stop(pid, "boot deadline")
                    stopped.append(pid)
            self._save()
        return stopped

    def reconcile(self) -> dict:
        out = {"adopted": 0, "destroyed": 0, "gone": 0}
        with self.lock:
            known = {(p["provider"], p["handle"]): pid for pid, p in self.table["placements"].items()}
            seen = set()
            for name, provider in self.providers.items():
                try:
                    found = provider.list()
                except Exception as e:
                    log(f"reconcile: {name} did not answer: {e}")
                    continue
                for h in found:
                    key = (name, h["id"])
                    seen.add(key)
                    if key in known:
                        out["adopted"] += 1
                    else:
                        log(f"reconcile: destroying {name} {h['id']} ({h.get('model')}): not in the table")
                        provider.stop(h["id"])
                        out["destroyed"] += 1
                for pid, p in list(self.table["placements"].items()):
                    if p["provider"] == name and (name, p["handle"]) not in seen:
                        self._ledger(p, "gone")
                        del self.table["placements"][pid]
                        out["gone"] += 1
            live = set(self.table["placements"])
            for lid in [lid for lid, lease in self.table["leases"].items() if lease["placement"] not in live]:
                del self.table["leases"][lid]
            self._save()
        return out

    def stop(self, pid: str, why: str = "asked") -> None:
        with self.lock:
            if pid not in self.table["placements"]:
                raise Refusal(f"no placement {pid}")
            self._stop(pid, why)
            self._save()

    def _stop(self, pid: str, why: str) -> None:
        p = self.table["placements"].pop(pid)
        for lid in [lid for lid, lease in self.table["leases"].items() if lease["placement"] == pid]:
            del self.table["leases"][lid]
        self.providers[p["provider"]].stop(p["handle"])
        self._ledger(p, why)
        self._save()
        log(f"{p['model']}: placement {pid} stopped: {why}")

    def _ledger(self, p: dict, why: str) -> None:
        now = self.clock()
        row = {"model": p["model"], "provider": p["provider"], "handle": p["handle"], "started": p["started"],
               "stopped": now, "rate_usd_h": p["rate_usd_h"], "cost_usd": round(p["rate_usd_h"] * (now - p["started"]) / 3600.0, 4),
               "why": why}
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def ledger(self) -> list[dict]:
        if not os.path.isfile(self.ledger_path):
            return []
        with open(self.ledger_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
