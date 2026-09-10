"""The run ledger: one JSON line per run.

Not for reporting: it is what makes the cost model's constants computable from
the runs themselves, and it collects the machines that already hold our image in
their docker cache.
"""
import json
import os
import time
from dataclasses import dataclass, asdict, field

from booksmith.core import knobs
from booksmith.core.log import log
from booksmith.core.page import write_json

# A relative path would lose the whole history when run from another directory,
# and the pick of warmed machines with it.
from booksmith.core.config import ROOT as _ROOT


def file() -> str:
    """Where the journal is, asked at each use and not at import so a job's
    own setting is honoured."""
    return knobs.knob("BOOKSMITH_LEDGER") or os.path.join(_ROOT, "runs", "ledger.jsonl")


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
    inet_down_adv: float = 0.0     # bandwidth the host advertises
    disk_bw: float = 0.0
    # vLLM start-up varies sixfold between identical cards (65 s against 374 s)
    # and neither link nor disk explains it: it is imports, compilation and
    # warm-up, that is, the processor.
    cpu_cores: float = 0.0
    cpu_ghz: float = 0.0
    link_mbps: float = 0.0         # measured link to us, not advertised
    # Our own downlink at the time of the run, measured over HTTPS. It decides:
    # the rejection floor is `min(limit, 0.5*ours)`, and the permanent blacklist
    # refuses to act when it is zero. `None` means not measured, not 0.0.
    our_downlink_mbps: float | None = None
    # Speed from the world. `None` means not measured, which is not 0.0, "the
    # probe failed": the probe runs only when the link to us clears a floor.
    # `fast_machines` tests the field truthily, so `None` is as false as 0.0.
    download_mbps: float | None = None
    image_gb: float = 0.0

    started: float = field(default_factory=time.time)
    setup_s: float = 0.0           # from the successful machine's creation to ssh
    reject_s: float = 0.0          # time spent on rejected ones before it
    # What the rejected machines cost and how many there were. Separate fields
    # rather than one sum in cost_usd: a run that died during renting never
    # reaches `dph` and would be written down as free.
    reject_usd: float = 0.0
    reject_n: int = 0
    run_s: float = 0.0             # the task itself
    total_s: float = 0.0
    cost_usd: float = 0.0
    ok: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    # No properties here: the ledger is written through `asdict(run)`, which
    # takes none, so anything computed would never reach the file.


def _ensure_dir(path: str) -> None:
    """The directory `path` will be written into, `.` when it has none.

    One copy for every caller: `BOOKSMITH_LEDGER` legitimately accepts a bare
    file name, whose dirname is empty, and `os.makedirs("")` raises.
    """
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
    """Machines where this image has already come up, freshest first.

    The docker cache lives on the physical machine, and so does vast's own ssh
    build on top, which costs more than the image: 34 seconds warm against six
    minutes. The mark of warmth is reaching ssh, not the task succeeding.
    """
    path = path or file()
    seen: dict[int, float] = {}
    for r in read(path):
        if (r.get("image") == image and r.get("machine_id")
                and float(r.get("setup_s") or 0) > 0):
            mid = int(r["machine_id"])
            seen[mid] = max(seen.get(mid, 0), r.get("started", 0))
    return [m for m, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def slow_machines(image: str, path: str = "",
                  job: str | None = None) -> list[int]:
    """Machines the ledger shows to be twice slower than the best.

    A separate function, because preferring warm machines otherwise cancels the
    selection: fast_machines drops a slow one and the warm list hands it back.
    Without `job` times are incomparable and no machine is marked slow.
    """
    path = path or file()
    fast = set(fast_machines(image, path, job))
    seen = set()
    for r in read(path):
        mid = r.get("machine_id")
        if (job and r.get("image") == image and mid and r.get("ok")
                and r.get("run_s") and r.get("job") == job):
            seen.add(int(mid))
    return sorted(seen - fast)


def fast_machines(image: str, path: str = "",
                  job: str | None = None) -> list[int]:
    """Machines sorted by measured speed, fastest first.

    Machines with an observed compute time under `job` rank by the median of it
    -- the median, not the maximum -- and the probe ranks the rest. Without
    `job` times are not compared at all. `run_s` is dominated by delivery, so
    what this ranks is the link, not the card, and a book's first run under a
    new `job` rejects nobody by time.
    """
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
        # Compute time is comparable only within one task: a machine that only
        # ever saw heavier weights would look slow for nothing.
        if job and r.get("ok") and r.get("run_s") and r.get("job") == job:
            times.setdefault(mid, []).append(float(r["run_s"]))

    def med(v):
        v = sorted(v)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    seen = set(probes) | set(times)
    # Those seen at work first, by time; then the rest by probe, more is better.
    ranked = sorted((m for m in seen if m in times), key=lambda m: med(times[m]))
    # A machine twice slower than the best is not preferred to an unknown one.
    if ranked:
        limit = 2 * med(times[ranked[0]])
        ranked = [m for m in ranked if med(times[m]) <= limit]
    ranked += sorted((m for m in seen if m not in times),
                     key=lambda m: -med(probes[m]))
    return ranked


def _read_bad(path: str) -> tuple[dict, str]:
    """(machine list, reason for distrust); an empty list and a broken file differ.

    Every record in the file is paid for by a rental, so "could not parse" must
    not be swallowed into an empty dict that the next write overwrites.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}, ""                       # no file -- legitimate emptiness
    except OSError as e:
        return {}, f"{type(e).__name__}: {e}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return {}, f"{type(e).__name__}: {str(e)[:80]} ({len(raw)} bytes)"
    if not isinstance(data, dict):
        return {}, (f"top level is {type(data).__name__}, an object is "
                    f"needed ({len(raw)} bytes)")
    return data, ""


def mark_bad(machine_id: int | None, reason: str, path: str = "") -> None:
    """Remember a machine that will not do -- forever, not for one run.

    Without it a machine we once reached ssh on counts as warm even when the link
    to it is 62 kbit/s. `machine_id` may arrive empty, an offer's field being
    optional: nothing to record then, and the run must not die over it either.
    """
    path = path or bad_file()
    try:
        key = str(int(machine_id))
    except (TypeError, ValueError):
        log(f"WARNING: cannot blacklist -- the offer has no machine_id "
            f"({machine_id!r}); the reason was: {reason}. "
            f"It can come again")
        return
    data, broken = _read_bad(path)
    if broken:
        # Broken content is set aside, not overwritten: each machine in it has
        # already cost a rental.
        keep = f"{path}.broken-{int(time.time())}"
        try:
            os.replace(path, keep)
        except OSError as e:
            keep = f"(could not set it aside: {e})"
        log(f"WARNING: blacklist {path} does not parse ({broken}) -- set "
            f"aside as {keep}, starting a clean one. Its machines return "
            f"to rentals until it is repaired by hand")
    data[key] = {"reason": reason, "ts": time.time()}
    _ensure_dir(path)
    write_json(path, data, indent=1)
    log(f"machine {key} blacklisted forever ({reason}); "
        f"{len(data)} in the list")


def bad_machines(path: str = "") -> list[int]:
    """Machines never to take again.

    Silent only when the list is empty: an unread list looks exactly like an
    empty one.
    """
    path = path or bad_file()
    data, broken = _read_bad(path)
    if broken:
        log(f"WARNING: blacklist {path} does not parse ({broken}) -- "
            f"taking it as EMPTY. Rejected machines return to rentals; "
            f"the file is in place, repair it by hand")
        return []
    out, skipped = [], 0
    for k in data:
        try:
            out.append(int(k))
        except (TypeError, ValueError):
            skipped += 1
    if skipped:
        log(f"WARNING: blacklist {path} holds {skipped} unreadable keys of "
            f"{len(data)} -- those machines are not filtered out")
    return out


def fit(path: str = "") -> dict:
    """Estimate LINK_EFFICIENCY from the actual runs, or refuse and say why.

    The estimate divides `image_gb * 8 * 1024 / setup_s` by the advertised link,
    so the numerator must vary -- a constant one measures the denominator -- and
    `setup_s` must measure delivery alone. Records of its old shape, recognised
    by the missing `reject_s`, are skipped one by one and the skip is counted;
    one of them must not cancel the count over all the others.
    """
    path = path or file()
    eff, gbs, old_shape = [], set(), 0
    for r in read(path):
        adv, setup, gb = r.get("inet_down_adv"), r.get("setup_s"), r.get("image_gb")
        if not (adv and setup and gb and setup > 0):
            continue
        if "reject_s" not in r:
            old_shape += 1
            continue
        gbs.add(round(float(gb), 3))
        eff.append((gb * 8 * 1024 / setup) / adv)
    # The skip is named in every answer, not only in a refusal: an estimate over
    # seven records of forty-eight is a different estimate from one over all.
    skipped = {"skipped_old_setup_s": old_shape} if old_shape else {}
    if len(gbs) < 2:
        return {"samples": len(eff), **skipped, "why_no_estimate":
                f"one image size in every record ({sorted(gbs) or '--'}): "
                f"the numerator is constant, and the division would measure "
                f"the denominator"}
    if len(eff) < 5:
        return {"samples": len(eff), **skipped, "why_no_estimate":
                "fewer than five usable records"}
    eff.sort()
    return {"samples": len(eff), **skipped, "distinct_image_sizes": len(gbs),
            "link_efficiency_median": eff[len(eff) // 2],
            "link_efficiency_p25": eff[len(eff) // 4]}


def totals(rows) -> dict:
    """Runs, successes and money over the journal rows."""
    return {"runs": len(rows),
            "ok": sum(1 for r in rows if r.get("ok")),
            "spent_usd": sum(r.get("cost_usd") or 0 for r in rows)}


def observed_mbps(row) -> float | None:
    """Delivery speed of one run from its image size and setup time, or None."""
    setup, gb = row.get("setup_s"), row.get("image_gb")
    if (setup or 0) > 0 and gb:
        return gb * 8 * 1024 / setup
    return None  # not 0: a run with no setup time is unmeasured, not infinitely fast
