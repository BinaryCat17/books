"""The run ledger: one JSON line per run.

Not for reporting. The cost model's constants (LINK_EFFICIENCY, UNPACK_RATIO)
were once fitted on two measurements and nailed into the code while the
measurements themselves were stored nowhere. The ledger makes them computable,
and collects the machines that already hold our image in their docker cache.
"""
import json
import os
import time
from dataclasses import dataclass, asdict, field

from ..run import knobs

# A relative path would silently lose the whole history when run from another
# directory, and the pick of warmed machines with it.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# Declared in the registry, or `books replay --check` cannot see that the
# ledger and the machine BLACKLIST moved elsewhere. This was the project's only
# read of the environment past the registry, and it dragged `bad-machines.json`
# along -- after which rejected machines went back into rentals.
LEDGER = knobs.knob("BOOKSMITH_LEDGER") or os.path.join(_ROOT, "runs", "ledger.jsonl")


def log(msg):
    """Our own `log`, not the shared one from `vast.py`, which drags in the
    `vastai` package: the ledger is read by `books ledger`, a command that
    rents nothing. Two lines are cheaper than the import, and `box.py` does
    the same.
    """
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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
    # vLLM start-up time varies sixfold between machines (65 s against 374 s on
    # identical RTX 4090s), and neither link nor disk explains it: almost all
    # of it is imports, compilation and warm-up, i.e. the CPU. Recorded so the
    # pick goes by measurement, not by guess.
    cpu_cores: float = 0.0
    cpu_ghz: float = 0.0
    link_mbps: float = 0.0         # MEASURED link to us, not advertised
    # Speed from the world. `None` means NOT MEASURED, which is not 0.0, "the
    # probe failed". The field used to be `float = 0.0` and both troubles were
    # written as one zero: the probe runs only when the link to us clears a
    # floor -- and before the fix in `runner._rent`, the REGISTRY floor rather
    # than the effective one. Three records in the current ledger carry
    # `link_mbps` > 0 with `download_mbps` = 0.0 (19.08 20:37, 20.08 13:08,
    # 20.08 22:54), and by them it cannot be told whether the machine was
    # measured at all. `fast_machines` tests the field truthily, so `None`
    # there is as false as 0.0 and the order of machines does not change.
    download_mbps: float | None = None
    image_gb: float = 0.0

    started: float = field(default_factory=time.time)
    setup_s: float = 0.0           # from create of a SUCCESSFUL machine to ssh
    reject_s: float = 0.0          # time spent on rejected ones before it
    # What the rejected machines COST and how many there were. Separate fields
    # rather than one sum in cost_usd: a run that died during renting was
    # written down as free (`dph` = 0, `rec.dph` never reached), and five taken
    # machines came to nothing. The current ledger holds 13 such records ("no
    # machine found in N attempts"), 9268 seconds of running for $0.102 between
    # them -- one traffic charge counted, and not a second of rent.
    reject_usd: float = 0.0
    reject_n: int = 0
    run_s: float = 0.0             # the task itself
    total_s: float = 0.0
    cost_usd: float = 0.0
    ok: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    # `observed_mbps` REMOVED. It computed image delivery speed and honestly
    # returned `None` when there was nothing to measure, but was unreachable by
    # construction: the ledger is written through `asdict(run)`, which takes no
    # properties, so it reached the file NOT ONCE. A second, live copy of the
    # arithmetic sat in `cli.py` and printed "0 Мбит/с" on an unmeasured run --
    # of the two copies the dead one held the right semantics. It moved into
    # the live one; the copy is gone.


def append(run: Run, path: str = LEDGER) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    d = asdict(run)
    d["started_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(run.started))
    with open(path, "a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def read(path: str = LEDGER) -> list[dict]:
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


def warm_machines(image: str, path: str = LEDGER) -> list[int]:
    """Machines where this image has already come up, freshest first.

    The docker cache lives on the physical machine, and so does vast's own ssh
    build on top -- which costs more than the image: a Debian index and near a
    hundred packages, 34 seconds on a warm machine against six minutes.

    The mark of warmth is reaching ssh (setup_s), not the task succeeding: the
    run that died on our own bug in the task code warmed the machine too.
    """
    seen: dict[int, float] = {}
    for r in read(path):
        if (r.get("image") == image and r.get("machine_id")
                and float(r.get("setup_s") or 0) > 0):
            mid = int(r["machine_id"])
            seen[mid] = max(seen.get(mid, 0), r.get("started", 0))
    return [m for m, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def slow_machines(image: str, path: str = LEDGER,
                  job: str | None = None) -> list[int]:
    """Machines the ledger shows to be twice slower than the best.

    A separate function, because preferring warm machines otherwise cancels the
    selection: fast_machines drops a slow one, the warm list hands it back, and
    it is rented as if nothing had happened -- so 110506 with its 909 seconds
    returned sixth, behind five fast ones.

    `job` carries the caveat of `fast_machines`: without a task name times are
    incomparable and not one machine is marked slow.
    """
    fast = set(fast_machines(image, path, job))
    seen = set()
    for r in read(path):
        mid = r.get("machine_id")
        if (job and r.get("image") == image and mid and r.get("ok")
                and r.get("run_s") and r.get("job") == job):
            seen.add(int(mid))
    return sorted(seen - fast)


def fast_machines(image: str, path: str = LEDGER,
                  job: str | None = None) -> list[int]:
    """Machines sorted by MEASURED speed, fastest first.

    Measure the machine, not the advertising. Offers are filtered on the
    advertised `inet_down>500`, and advertising it is: the run that took
    machine 110506 on a promise above 500 got 96 Mbit/s and computed 909
    seconds instead of 300.

    The median, not the maximum: machine 18857 once gave 1140 Mbit/s, but its
    six probes are 33, 104, 154, 307, 319, 1140.

    Honest caveat: the probe predicts run time poorly, correlation over the
    ledger only -0.42, so machines with an observed compute time rank by that
    and the probe is a fallback for those seen once.

    WHAT IS ACTUALLY MEASURED HERE. `run_s` is delivery plus vLLM start-up plus
    compute, and the first term dominates. Machine 110506, on which both
    functions rest ("909 seconds where 136645 fits in 212"), has
    `extra.pages_per_sec` = 0.819 at `vllm_startup_s` = 123 -- 24.4 s of
    compute over twenty pages, the same order as 51608 (0.79) on that task; the
    other 760 seconds went on wheels and weights. So ranking by `run_s` prefers
    a wide link, not a fast card: legitimate for the total cost of a run, but
    calling the result "a slow machine" is untrue, and these docstrings used to
    do it. The clean compute measure lies beside it, `extra.pages_per_sec`,
    filled in 59 records of 95 -- still not comparable BETWEEN BOOKS: 51608
    reads 0.79 on twenty pages of tables and 2.0 on Feynman, pages of different
    density, not a machine of different speed.

    `job` says which task counts as comparable, and it is the caller's to
    choose: the job name, exactly as it lands in the record. It used to be
    `job.startswith("tables")`, a twenty-page bench that no longer exists, and
    the hardcode would now pick zero records silently. Without `job` times are
    not used at all -- there is nothing to compare with what, and the probe is
    honester than an invented order. The price, stated plainly: a new book's
    FIRST run has no history under that `job` and rejects nobody by time. A
    limitation, not a defence, and `runner._warm` prints it as a number so it
    does not look like work.
    """
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
        # ever saw a model with four times heavier weights would look slow for
        # nothing.
        if job and r.get("ok") and r.get("run_s") and r.get("job") == job:
            times.setdefault(mid, []).append(float(r["run_s"]))

    def med(v):
        v = sorted(v)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    seen = set(probes) | set(times)
    # First those seen at work -- by time, less is better. Then the rest -- by
    # probe, more is better.
    ranked = sorted((m for m in seen if m in times), key=lambda m: med(times[m]))
    # A machine twice slower than the best must not be preferred to an unknown
    # one: 110506 computed 909 seconds where 136645 fits in 212.
    if ranked:
        limit = 2 * med(times[ranked[0]])
        ranked = [m for m in ranked if med(times[m]) <= limit]
    ranked += sorted((m for m in seen if m not in times),
                     key=lambda m: -med(probes[m]))
    return ranked


BAD = os.path.join(os.path.dirname(LEDGER), "bad-machines.json")


def _read_bad(path: str) -> tuple[dict, str]:
    """(machine list, reason for distrust). An empty list and a BROKEN file
    are different things.

    Both functions below used to swallow any exception and carry on with an
    empty dict. The price: a broken `bad-machines.json` silently switched the
    blacklist off entirely, and the first `mark_bad` wrote ONE machine over it,
    the rest gone for good. Every record in that file is paid for by a rental,
    so "could not parse" must sound different from "empty".
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
        return {}, f"{type(e).__name__}: {str(e)[:80]} ({len(raw)} байт)"
    if not isinstance(data, dict):
        return {}, (f"на верхнем уровне {type(data).__name__}, а нужен объект "
                    f"({len(raw)} байт)")
    return data, ""


def mark_bad(machine_id: int | None, reason: str, path: str = BAD) -> None:
    """Remember a machine that will not do -- forever, not for one run.

    Without it, preferring warm machines walks straight into the rake: a
    machine we once reached ssh on counts as warm even when the link to it is
    62 kbit/s. That is what happened, and it cost fifteen minutes of rent.

    `machine_id` may arrive empty, the field being optional on an offer, and
    then there is nothing to record -- but the run must not die either, and
    `int(None)` used to fly out of the middle of the rent loop and take the
    WHOLE run with it, machine already taken (`runner._rent`, the branch that
    rejects by link).
    """
    try:
        key = str(int(machine_id))
    except (TypeError, ValueError):
        log(f"ВНИМАНИЕ: машину в чёрный список НЕ записать — оффер без "
            f"machine_id ({machine_id!r}); причина была: {reason}. "
            f"Эта машина может прийти снова")
        return
    data, broken = _read_bad(path)
    if broken:
        # Broken content is set aside, not overwritten: it holds machines, each
        # of which has already cost a rental.
        keep = f"{path}.broken-{int(time.time())}"
        try:
            os.replace(path, keep)
        except OSError as e:
            keep = f"(отложить не удалось: {e})"
        log(f"ВНИМАНИЕ: чёрный список {path} не разбирается ({broken}) — "
            f"отложен в {keep}, дальше пишу с чистого листа. Машины из него "
            f"снова пойдут в аренду, пока файл не починят руками")
    data[key] = {"reason": reason, "ts": time.time()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    log(f"машина {key} в чёрном списке навсегда ({reason}); всего в списке "
        f"{len(data)}")


def bad_machines(path: str = BAD) -> list[int]:
    """Machines never to take again. Silent only when the list is empty: an
    unread list looks exactly like an empty one, and it is worth five rejected
    rentals.
    """
    data, broken = _read_bad(path)
    if broken:
        log(f"ВНИМАНИЕ: чёрный список {path} не разбирается ({broken}) — "
            f"считаю его ПУСТЫМ. Отбракованные машины снова пойдут в аренду; "
            f"файл на месте, почините руками")
        return []
    out, skipped = [], 0
    for k in data:
        try:
            out.append(int(k))
        except (TypeError, ValueError):
            skipped += 1
    if skipped:
        log(f"ВНИМАНИЕ: в чёрном списке {path} непонятных ключей {skipped} "
            f"из {len(data)} — эти машины не отсеиваются")
    return out


def fit(path: str = LEDGER) -> dict:
    """Estimate LINK_EFFICIENCY from the actual runs.

    REFUSES TO COMPUTE when there is nothing to compute from, and says why.

    The estimate divides `image_gb * 8 * 1024 / setup_s` by the advertised
    link. Two conditions, both of which used to break silently:

    * **the numerator must vary.** In every record of the current ledger
      `image_gb` is 0.06, one constant, and dividing a constant by a varying
      denominator measures the denominator, not the link.
    * **the denominator must measure delivery.** Before the fix `setup_s`
      measured the whole run-up: the probe of our own link, EVERY rejected
      attempt, each offer search and both probes. Hence a median of 0.0052
      against the constant 0.05 it was meant to confirm -- a tenfold gap,
      purely arithmetic, printed as a healthy number.

    Records of the old `setup_s` shape are recognised by the missing `reject_s`
    field and SKIPPED, the skip printed as a number. Skipped, not disabling the
    estimate: `if old_shape: return` stood here, so ONE old record cancelled
    the count over all the others forever -- the ledger only grows -- and
    `books ledger` called 41 records uncountable while 70 of the new shape sat
    beside them, the docstring meanwhile promising the opposite.
    """
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
    # The skip is named in EVERY answer, not only in a refusal: an estimate
    # over seven records of forty-eight and one over all forty-eight are
    # different estimates, and the difference must show without opening code.
    skipped = {"skipped_old_setup_s": old_shape} if old_shape else {}
    if len(gbs) < 2:
        return {"samples": len(eff), **skipped, "why_no_estimate":
                f"размер образа во всех записях один ({sorted(gbs) or '—'}): "
                f"числитель постоянен, и деление мерило бы знаменатель"}
    if len(eff) < 5:
        return {"samples": len(eff), **skipped, "why_no_estimate":
                "меньше пяти пригодных записей"}
    eff.sort()
    return {"samples": len(eff), **skipped, "distinct_image_sizes": len(gbs),
            "link_efficiency_median": eff[len(eff) // 2],
            "link_efficiency_p25": eff[len(eff) // 4]}
