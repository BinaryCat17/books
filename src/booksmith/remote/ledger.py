"""Журнал прогонов: одна строка JSON на прогон.

Смысл не в отчётности.  Константы модели стоимости (LINK_EFFICIENCY,
UNPACK_RATIO) раньше были подобраны по двум замерам и вбиты в код, а сами
замеры нигде не хранились.  Журнал делает их вычислимыми — и заодно копит
список машин, которые уже держат наш образ в кеше docker.
"""
import json
import os
import time
from dataclasses import dataclass, asdict, field

# Относительный путь молча терял бы всю историю при запуске из другого
# каталога, а вместе с ней и подбор прогретых машин.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LEDGER = os.environ.get("BOOKSMITH_LEDGER", os.path.join(_ROOT, "runs", "ledger.jsonl"))


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
    inet_down_adv: float = 0.0     # заявленная хостом полоса
    disk_bw: float = 0.0
    # Разброс времени старта vLLM между машинами — шестикратный (65с против
    # 374с на одинаковых RTX 4090), и он не объясняется ни каналом, ни
    # диском: почти всё это импорты, компиляция и прогрев, то есть процессор.
    # Пишем его, чтобы выбирать по замеру, а не по догадке.
    cpu_cores: float = 0.0
    cpu_ghz: float = 0.0
    link_mbps: float = 0.0         # ЗАМЕРЕННЫЙ канал до нас, не заявленный
    image_gb: float = 0.0

    started: float = field(default_factory=time.time)
    setup_s: float = 0.0           # от create до готового ssh
    run_s: float = 0.0             # сама задача
    total_s: float = 0.0
    cost_usd: float = 0.0
    ok: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def observed_mbps(self) -> float | None:
        """Фактическая скорость доставки образа, Мбит/с."""
        if self.setup_s <= 0 or not self.image_gb:
            return None
        return self.image_gb * 8 * 1024 / self.setup_s


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
    """Машины, где этот образ уже поднимался, свежие первыми.

    Кеш docker живёт на физической машине, и там же остаётся достройка vast
    со своим ssh — а она дороже самого образа: индекс Debian и под сотню
    пакетов.  Замерено: 34 секунды на прогретой машине против шести минут.

    Признак прогретости — что мы дошли до ssh (setup_s), а не что задача
    удалась: машина прогрелась и в том прогоне, который упал на нашей же
    ошибке в коде задачи.
    """
    seen: dict[int, float] = {}
    for r in read(path):
        if (r.get("image") == image and r.get("machine_id")
                and float(r.get("setup_s") or 0) > 0):
            mid = int(r["machine_id"])
            seen[mid] = max(seen.get(mid, 0), r.get("started", 0))
    return [m for m, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


BAD = os.path.join(os.path.dirname(LEDGER), "bad-machines.json")


def mark_bad(machine_id: int, reason: str, path: str = BAD) -> None:
    """Запомнить машину, которая не годится, — навсегда, а не на прогон.

    Без этого предпочтение прогретых машин ведёт прямо на грабли: машина,
    где мы однажды дошли до ssh, считается прогретой, даже если канал до неё
    62 кбит/с.  Ровно так и вышло — и стоило пятнадцати минут аренды.
    """
    data = {}
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        pass
    data[str(int(machine_id))] = {"reason": reason, "ts": time.time()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def bad_machines(path: str = BAD) -> list[int]:
    try:
        with open(path) as f:
            return [int(k) for k in json.load(f)]
    except Exception:
        return []


def fit(path: str = LEDGER) -> dict:
    """Оценить LINK_EFFICIENCY по фактическим прогонам.

    Возвращает пустой словарь, пока данных мало — лучше пользоваться
    пессимистичной константой, чем средним по двум точкам.
    """
    eff = []
    for r in read(path):
        adv, setup, gb = r.get("inet_down_adv"), r.get("setup_s"), r.get("image_gb")
        if adv and setup and gb and setup > 0:
            eff.append((gb * 8 * 1024 / setup) / adv)
    if len(eff) < 5:
        return {"samples": len(eff)}
    eff.sort()
    return {"samples": len(eff), "link_efficiency_median": eff[len(eff) // 2],
            "link_efficiency_p25": eff[len(eff) // 4]}
