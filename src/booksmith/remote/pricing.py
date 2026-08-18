"""Сколько на самом деле стоит прогон, и какой оффер выбрать.

Ранжировать по $/час неправильно сразу по двум причинам, и обе измерены,
а не выведены из общих соображений:

1. Холодный старт — это не только скачивание, но и распаковка образа.
   Хост с медленным диском стопорится после "Download complete".
2. **Трафик стоит денег.** Проверено по 41 офферу RTX 4090: цена входящего
   трафика ненулевая у всех, от $0.4 до $29.3 за ТБ при медиане $2.7.
   Один pull образа на 5.9 ГБ — это от $0.002 до $0.17.  На дорогом хосте
   скачивание образа стоит больше, чем весь счёт за работу.
"""
from dataclasses import dataclass

# docker тянет слои по три, но внутри слоя — одно HTTP-соединение.  В нашем
# образе один слой на 3.69 ГБ (62%) и второй на 1.54 ГБ (26%), то есть реально
# работают два потока, а не три.  Одиночный поток упирается не в полосу, а в
# RTT: заявленные Мбит/с реализуются процентов на десять.  Отсюда и потолок.
LINK_EFFICIENCY = 0.10
LINK_CEILING_MBPS = 2400.0     # быстрее одиночного потока не бывает
UNPACK_RATIO = 3.0             # 5.9 ГБ сжатого -> ~18 ГБ на диске
BOOT_SECONDS = 90.0            # sshd, инициализация контейнера vast


@dataclass
class Estimate:
    setup_s: float
    compute_s: float
    rent_usd: float
    traffic_usd: float

    @property
    def total_usd(self) -> float:
        return self.rent_usd + self.traffic_usd

    @property
    def total_s(self) -> float:
        return self.setup_s + self.compute_s


def estimate(offer: dict, image_gb: float, minutes: float,
             link_efficiency: float = LINK_EFFICIENCY,
             unpack_ratio: float = UNPACK_RATIO) -> Estimate:
    down = max(float(offer.get("inet_down") or 100), 50.0)
    effective = min(down * link_efficiency, LINK_CEILING_MBPS)
    dl_s = image_gb * 8 * 1024 / effective

    disk = max(float(offer.get("disk_bw") or 500), 100.0)
    unpack_s = image_gb * unpack_ratio * 1024 / disk * 60

    setup_s = dl_s + unpack_s + BOOT_SECONDS
    compute_s = minutes * 60
    rent = float(offer["dph_total"]) * (setup_s + compute_s) / 3600

    # `internet_down_cost_per_tb` — цена за терабайт; образ считаем один раз.
    per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
    traffic = image_gb / 1024 * per_tb
    return Estimate(setup_s, compute_s, rent, traffic)


def rank(offers: list[dict], image_gb: float, minutes: float, **kw) -> list[dict]:
    """Офферы по возрастанию полной стоимости прогона, с полем `_est`."""
    out = []
    for o in offers:
        e = estimate(o, image_gb, minutes, **kw)
        out.append({**o, "_est": e})
    return sorted(out, key=lambda o: o["_est"].total_usd)


def describe(offer: dict) -> str:
    e = offer["_est"]
    return (f"#{offer['id']}  ${offer['dph_total']:.3f}/час  "
            f"{offer.get('inet_down', 0):.0f} Мбит  "
            f"{offer.get('disk_bw', 0):.0f} МБ/с диск  "
            f"${offer.get('internet_down_cost_per_tb') or 0:.1f}/ТБ  "
            f"старт~{e.setup_s/60:.1f}мин  "
            f"=> ${e.total_usd:.3f} (аренда {e.rent_usd:.3f} + трафик {e.traffic_usd:.3f})  "
            f"машина {offer.get('machine_id')}")
