import os
import time

from fleet.errors import Refusal
from fleet.log import log

PREFIX = "bs-svc-"


def key_present() -> bool:
    if os.environ.get("VAST_API_KEY"):
        return True
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return any(os.path.isfile(p) for p in (os.path.join(xdg, "vastai", "vast_api_key"),
                                           os.path.join(os.path.expanduser("~"), ".vast_api_key")))


def query(entry: dict) -> str:
    q = [f"gpu_name={entry.get('gpu_name') or 'RTX_4090'}", "num_gpus=1", "rentable=true", "verified=true",
         f"reliability>{entry.get('min_reliability', 0.98)}", f"dph_total<{entry.get('max_dph', 0.6)}",
         f"inet_down>{entry.get('min_down_mbps', 500)}", f"disk_space>{entry.get('disk_gb', 40)}"]
    if entry.get("cuda_min"):
        q.append(f"cuda_vers>={entry['cuda_min']}")
    return " ".join(q)


class Vast:
    name = "vast"

    def __init__(self, sdk=None):
        if sdk is None:
            from vastai import VastAI

            sdk = VastAI(retry=1)
        self.v = sdk

    def available(self) -> bool:
        try:
            self.v.show_user()
            return True
        except Exception:
            return False

    def offers(self, entry: dict) -> list[dict]:
        found = self.v.search_offers(query(entry), order="dph_total", storage=float(entry.get("disk_gb", 40)))
        return sorted(found or [], key=lambda o: float(o.get("dph_total") or 9e9))

    def start(self, model: str, entry: dict, key: str) -> dict:
        offers = self.offers(entry)
        if not offers:
            raise Refusal(f"{model}: no offer for {query(entry)}")
        offer = offers[0]
        port = entry["port"]
        env = " ".join([f"-p {port}:{port}", f"-e BOOKSMITH_SERVE_KEY={key}", f"-e BOOKSMITH_PORT={port}",
                        f"-e BOOKSMITH_IDLE_S={int(entry['idle_s'] * 2 + 600)}"]
                       + [f"-e {k}={v}" for k, v in entry["env"].items()])
        res = self.v.create_instance(id=int(offer["id"]), image=entry["image"], disk=float(entry.get("disk_gb", 40)),
                                     label=PREFIX + model, env=env, runtype="args", cancel_unavail=True)
        iid = res.get("new_contract") if isinstance(res, dict) else None
        if not iid:
            raise Refusal(f"{model}: vast did not create the instance: {res}")
        log(f"{model}: instance {iid} created on machine {offer.get('machine_id')} at ${offer.get('dph_total')}/h")
        return {"id": str(iid), "endpoint": "", "rate_usd_h": float(offer.get("dph_total") or 0.0)}

    def endpoint(self, handle: str, port: int) -> str:
        inst = self.v.show_instance(id=int(handle)) or {}
        if isinstance(inst, list):
            inst = inst[0] if inst else {}
        if inst.get("actual_status") in ("exited", "offline"):
            raise Refusal(f"instance {handle} died: {inst.get('status_msg')}")
        ip = inst.get("public_ipaddr")
        mapped = ((inst.get("ports") or {}).get(f"{port}/tcp") or [{}])[0].get("HostPort")
        return f"http://{str(ip).strip()}:{mapped}" if ip and mapped else ""

    def _row(self, handle: str) -> dict | None:
        return next((i for i in self.v.show_instances() if str(i.get("id")) == str(handle)), None)

    def alive(self, handle: str) -> bool:
        try:
            row = self.v.show_instance(id=int(handle))
        except Exception:
            return True
        if isinstance(row, list):
            row = row[0] if row else None
        return bool(row) and row.get("actual_status") not in ("exited", "offline")

    def stop(self, handle: str) -> None:
        for pause in (0, 4, 8, 16, 32, 60):
            time.sleep(pause)
            try:
                self.v.destroy_instance(id=int(handle))
            except Exception as e:
                log(f"destroy {handle}: {e}")
            try:
                if self._row(handle) is None:
                    return
            except Exception:
                continue
        raise Refusal(f"instance {handle} is still there after every attempt to destroy it")

    def list(self) -> list[dict]:
        rows = self.v.show_instances()
        return [{"id": str(i["id"]), "model": (i.get("label") or "")[len(PREFIX):], "state": i.get("actual_status", "")}
                for i in rows if (i.get("label") or "").startswith(PREFIX)]

