import json
import os
import time
from dataclasses import dataclass, asdict, field
from fleet import knobs
from fleet.log import log
from fleet.files import write_json
from fleet import settings


def file() -> str:
    return knobs.knob("BOOKSMITH_LEDGER") or os.path.join(settings.home(), "runs", "ledger.jsonl")


def bad_file() -> str:
    return os.path.join(os.path.dirname(file()), "bad-machines.json")


@dataclass
class Run:
    job: str
    image: str
    gpu: str
    instance_id: int | None = None
    machine_id: int | None = None
    offer_id: int | None = None
    dph: float = 0.0
    per_tb: float = 0.0
    inet_down_adv: float = 0.0
    disk_bw: float = 0.0
    cpu_cores: float = 0.0
    cpu_ghz: float = 0.0
    link_mbps: float = 0.0
    our_downlink_mbps: float | None = None
    download_mbps: float | None = None
    image_gb: float = 0.0
    started: float = field(default_factory=time.time)
    setup_s: float = 0.0
    reject_s: float = 0.0
    reject_usd: float = 0.0
    reject_n: int = 0
    run_s: float = 0.0
    total_s: float = 0.0
    cost_usd: float = 0.0
    ok: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def append(run: Run, path: str = "") -> None:
    path = path or file()
    _ensure_dir(path)
    d = asdict(run)
    d["started_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(run.started))
    with open(path, "a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def read(path: str = "") -> list[dict]:
    path = path or file()
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def warm_machines(image: str, path: str = "") -> list[int]:
    path = path or file()
    seen: dict[int, float] = {}
    for r in read(path):
        if r.get("image") == image and r.get("machine_id") and (float(r.get("setup_s") or 0) > 0):
            mid = int(r["machine_id"])
            seen[mid] = max(seen.get(mid, 0), r.get("started", 0))
    return [m for m, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def slow_machines(image: str, path: str = "", job: str | None = None) -> list[int]:
    path = path or file()
    fast = set(fast_machines(image, path, job))
    seen = set()
    for r in read(path):
        mid = r.get("machine_id")
        if (
            job
            and r.get("image") == image
            and mid
            and r.get("ok")
            and r.get("run_s")
            and (r.get("job") == job)
        ):
            seen.add(int(mid))
    return sorted(seen - fast)


def fast_machines(image: str, path: str = "", job: str | None = None) -> list[int]:
    path = path or file()
    probes: dict[int, list[float]] = {}
    times: dict[int, list[float]] = {}
    bad = set(bad_machines())
    for r in read(path):
        mid = r.get("machine_id")
        if r.get("image") != image or not mid or int(mid) in bad:
            continue
        mid = int(mid)
        if r.get("download_mbps"):
            probes.setdefault(mid, []).append(float(r["download_mbps"]))
        if job and r.get("ok") and r.get("run_s") and (r.get("job") == job):
            times.setdefault(mid, []).append(float(r["run_s"]))

    def med(v):
        v = sorted(v)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    seen = set(probes) | set(times)
    ranked = sorted((m for m in seen if m in times), key=lambda m: med(times[m]))
    if ranked:
        limit = 2 * med(times[ranked[0]])
        ranked = [m for m in ranked if med(times[m]) <= limit]
    ranked += sorted((m for m in seen if m not in times), key=lambda m: -med(probes[m]))
    return ranked


def _read_bad(path: str) -> tuple[dict, str]:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return ({}, "")
    except OSError as e:
        return ({}, f"{type(e).__name__}: {e}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return ({}, f"{type(e).__name__}: {str(e)[:80]} ({len(raw)} bytes)")
    if not isinstance(data, dict):
        return ({}, f"top level is {type(data).__name__}, an object is needed ({len(raw)} bytes)")
    return (data, "")


def mark_bad(machine_id: int | None, reason: str, path: str = "") -> None:
    path = path or bad_file()
    try:
        key = str(int(machine_id))
    except (TypeError, ValueError):
        log(
            f"WARNING: cannot blacklist -- the offer has no machine_id ({machine_id!r}); the reason was: {reason}. It can come again"
        )
        return
    data, broken = _read_bad(path)
    if broken:
        keep = f"{path}.broken-{int(time.time())}"
        try:
            os.replace(path, keep)
        except OSError as e:
            keep = f"(could not set it aside: {e})"
        log(
            f"WARNING: blacklist {path} does not parse ({broken}) -- set aside as {keep}, starting a clean one. Its machines return to rentals until it is repaired by hand"
        )
    data[key] = {"reason": reason, "ts": time.time()}
    _ensure_dir(path)
    write_json(path, data, indent=1)
    log(f"machine {key} blacklisted forever ({reason}); {len(data)} in the list")


def bad_machines(path: str = "") -> list[int]:
    path = path or bad_file()
    data, broken = _read_bad(path)
    if broken:
        log(
            f"WARNING: blacklist {path} does not parse ({broken}) -- taking it as EMPTY. Rejected machines return to rentals; the file is in place, repair it by hand"
        )
        return []
    out, skipped = ([], 0)
    for k in data:
        try:
            out.append(int(k))
        except (TypeError, ValueError):
            skipped += 1
    if skipped:
        log(
            f"WARNING: blacklist {path} holds {skipped} unreadable keys of {len(data)} -- those machines are not filtered out"
        )
    return out
