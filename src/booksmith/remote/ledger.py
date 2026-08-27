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

from ..run import knobs

# Относительный путь молча терял бы всю историю при запуске из другого
# каталога, а вместе с ней и подбор прогретых машин.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# Ручка объявлена в реестре: `books replay --check` иначе не увидит, что
# журнал и ЧЁРНЫЙ СПИСОК машин уехали в другой каталог. Чтение окружения мимо
# реестра было здесь единственным во всём проекте — и уводило за собой
# `bad-machines.json`, после чего отбракованные машины снова шли в аренду.
LEDGER = knobs.knob("BOOKSMITH_LEDGER") or os.path.join(_ROOT, "runs", "ledger.jsonl")


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
    download_mbps: float = 0.0     # и ЗАМЕРЕННАЯ скорость машины из мира
    image_gb: float = 0.0

    started: float = field(default_factory=time.time)
    setup_s: float = 0.0           # от create УДАВШЕЙСЯ машины до готового ssh
    reject_s: float = 0.0          # сколько до неё ушло на отбракованные
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


def slow_machines(image: str, path: str = LEDGER,
                  job: str | None = None) -> list[int]:
    """Машины, которые по журналу вдвое медленнее лучшей.

    Отдельная функция, потому что предпочтение прогретых машин иначе сводит
    отбор на нет: fast_machines выбрасывает медленную, а список прогретых
    возвращает её следом, и она снимается как ни в чём не бывало.  Так
    вернулась 110506 со своими 909 секундами — шестым номером после пяти
    быстрых.

    `job` — та же оговорка, что у `fast_machines`: без имени задачи времена
    несравнимы, и медленных не выделяется ни одной.
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
    """Машины, отсортированные по замеренной скорости, самые быстрые первыми.

    Мерить надо не рекламу, а машину.  Отбор офферов идёт по заявленному
    `inet_down>500`, и это именно реклама: прогон, снявший машину 110506 с
    обещанием больше 500, получил 96 Мбит/с и считал 909 секунд вместо 300.

    Считается медиана, а не максимум: машина 18857 однажды дала 1140 Мбит/с,
    но её шесть замеров это 33, 104, 154, 307, 319, 1140 — по максимуму она
    попала бы в лучшие, по медиане стоит там, где заслуживает.

    Оговорка честная: сам зонд предсказывает время прогона слабо, корреляция
    по журналу всего -0.42.  Поэтому машины с наблюдённым временем счёта
    ранжируются по нему, а зонд остаётся запасной мерой для тех, кого мы
    видели один раз.

    ЧТО ЗДЕСЬ МЕРИТСЯ НА САМОМ ДЕЛЕ.  `run_s` — это доставка плюс подъём
    vLLM плюс счёт, и первое слагаемое господствует.  Машина 110506, которой
    обоснованы обе функции («909 секунд там, где 136645 укладывается в 212»),
    по журналу имеет `extra.pages_per_sec` = 0.819 при `vllm_startup_s` = 123,
    то есть 24.4 с собственно счёта на двадцати страницах — тот же разряд, что
    у 51608 (0.79) на той же задаче.  Остальные 760 секунд ушли на колёса и
    веса.  Значит ранжирование по `run_s` предпочитает машину с широким
    каналом, а не быструю карту; для полной стоимости прогона это законно, но
    называть результат «медленной машиной» — неправда, и докстринги её
    говорили.  Чистая мера счёта лежит рядом в журнале: `extra.pages_per_sec`,
    заполнено в 59 записях из 95.  Сравнивать её между КНИГАМИ всё равно
    нельзя: у 51608 она 0.79 на двадцати страницах таблиц и 2.0 на Фейнмане —
    страницы разной плотности, а не машина разной скорости.

    Какую задачу считать сравнимой, решает вызывающий: `job` — имя задания,
    ровно то, что попадёт в запись журнала.  Прежде здесь стояло
    `job.startswith("tables")` — имя стенда из двадцати страниц, по которому
    тогда мерили.  Стенда больше нет, и хардкод выбирал бы ноль записей
    молча, ничего не сообщая: список машин просто стал бы пустым, а причину
    никто бы не увидел.  Без `job` времена не используются вовсе — сравнивать
    нечего с чем, и зонд честнее выдуманного порядка.  Цена этого решения
    названа прямо: у ПЕРВОГО прогона новой книги истории с таким `job` нет,
    и по времени не отбраковывается никто.  Это ограничение, а не защита; оно
    печатается числом в `runner._warm`, чтобы не выглядело работой.
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
        # Время счёта сравнимо только внутри одной задачи: у модели с
        # вчетверо более тяжёлыми весами машина, видевшая только её,
        # выглядела бы медленной ни за что.
        if job and r.get("ok") and r.get("run_s") and r.get("job") == job:
            times.setdefault(mid, []).append(float(r["run_s"]))

    def med(v):
        v = sorted(v)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    seen = set(probes) | set(times)
    # Сначала те, кого мы видели за работой — по времени, меньше значит лучше.
    # Затем остальные — по зонду, больше значит лучше.
    ranked = sorted((m for m in seen if m in times), key=lambda m: med(times[m]))
    # Машину, которая вдвое медленнее лучшей, предпочитать незнакомой нельзя:
    # 110506 считала 909 секунд там, где 136645 укладывается в 212.
    if ranked:
        limit = 2 * med(times[ranked[0]])
        ranked = [m for m in ranked if med(times[m]) <= limit]
    ranked += sorted((m for m in seen if m not in times),
                     key=lambda m: -med(probes[m]))
    return ranked


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

    ОТКАЗЫВАЕТСЯ СЧИТАТЬ, когда считать не из чего, и говорит почему.

    Оценка делит `image_gb * 8 * 1024 / setup_s` на объявленный канал. У неё
    два условия, и оба нарушались молча:

    * **числитель должен меняться.** Во всех записях нынешнего журнала
      `image_gb` равен 0.06 — одна и та же константа. Делить константу на
      меняющийся знаменатель значит мерить знаменатель, а не эффективность
      канала.
    * **знаменатель должен мерить доставку.** До правки `setup_s` мерил весь
      разбег прогона: замер нашего канала, ВСЕ отбракованные попытки, каждый
      поиск предложений и оба зонда. Отсюда медиана 0.0052 против константы
      0.05, которую эта оценка и должна была подтвердить, — расхождение в
      десять раз, целиком арифметическое, печаталось как здоровое число.

    Записи со старым устройством `setup_s` отличаются отсутствием поля
    `reject_s`; они в оценку не идут.
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
    if old_shape:
        return {"samples": 0, "почему нет оценки":
                f"{old_shape} записей со старым setup_s (он мерил весь разбег "
                f"прогона, а не доставку образа) — по ним считать нельзя"}
    if len(gbs) < 2:
        return {"samples": len(eff), "почему нет оценки":
                f"размер образа во всех записях один ({sorted(gbs) or '—'}): "
                f"числитель постоянен, и деление мерило бы знаменатель"}
    if len(eff) < 5:
        return {"samples": len(eff), "почему нет оценки":
                "меньше пяти пригодных записей"}
    eff.sort()
    return {"samples": len(eff), "разных размеров образа": len(gbs),
            "link_efficiency_median": eff[len(eff) // 2],
            "link_efficiency_p25": eff[len(eff) // 4]}
