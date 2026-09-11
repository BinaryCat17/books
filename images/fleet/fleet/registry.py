import json
import os

from fleet import settings
from fleet.errors import Refusal
from fleet.files import write_json

KINDS = ("layout", "reader", "hybrid")
PROVIDERS = ("docker", "vast")
DEFAULTS = {"idle_s": 600, "budget_usd": 0.0, "port": 8000, "knobs": {}, "env": {}, "gpu": ""}


def check(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise Refusal("the registry is a mapping of names to entries")
    out = {}
    for name, e in raw.items():
        if not isinstance(e, dict) or e.get("kind") not in KINDS:
            raise Refusal(f"{name}: an entry names a kind, one of {KINDS}")
        has_endpoint, has_image = bool(e.get("endpoint")), bool(e.get("image"))
        if has_endpoint == has_image:
            raise Refusal(f"{name}: an endpoint or an image with a provider, not both and not neither")
        if has_image and not e.get("provider"):
            raise Refusal(f"{name}: an image names its provider; the fleet knows {PROVIDERS}")
        if has_image and e["provider"] == "vast" and not float(e.get("budget_usd") or 0) > 0:
            raise Refusal(f"{name}: a rented model needs a budget in dollars")
        if not isinstance(e.get("knobs", {}), dict) or not isinstance(e.get("env", {}), dict):
            raise Refusal(f"{name}: knobs and env are mappings")
        entry = {**DEFAULTS, **e}
        entry["knobs"] = {k: str(v) for k, v in entry["knobs"].items()}
        entry["env"] = {k: str(v) for k, v in entry["env"].items()}
        entry["idle_s"] = float(entry["idle_s"])
        entry["budget_usd"] = float(entry["budget_usd"])
        entry["port"] = int(entry["port"])
        out[name] = entry
    return out


def path() -> str:
    return os.path.join(settings.home(), "models.json")


def load() -> dict:
    if not os.path.isfile(path()):
        return {}
    with open(path(), encoding="utf-8") as f:
        return check(json.load(f))


def save(raw: object) -> dict:
    checked = check(raw)
    write_json(path(), checked, indent=1)
    return checked
