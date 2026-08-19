"""Сколько на самом деле стоит прогон, и какой оффер выбрать.

Ранжировать по $/час неправильно, и обе причины измерены, а не выведены из
общих соображений:

1. **Холодный старт стоит денег.** Он идёт по двум разным каналам, и они
   отличаются на порядок: образ едет через docker, всё остальное — мимо.
2. **Трафик стоит денег.** Проверено по 41 офферу RTX 4090: цена входящего
   трафика ненулевая у всех, от $0.4 до $29.3 за ТБ при медиане $2.7.
   На дорогом хосте доставка окружения стоит больше, чем сам счёт за работу.
"""
from dataclasses import dataclass

# --------------------------------------------------------------- через docker
# Три слоя одновременно, внутри слоя одно HTTP-соединение, и реестр режет
# соединение до ~25 Мбит/с.  Замер: 6.02 ГБ ехали 10.7 минуты на машине с
# каналом 1518 Мбит/с — 76 Мбит/с, пять процентов линка.
DOCKER_EFFICIENCY = 0.05
DOCKER_CEILING_MBPS = 120.0

# Распаковка: gzip внутри слоя однопоточный, и слои накладываются строго по
# одному, поверх предыдущего.  Замер на том же образе: после "Download
# complete" прошло ещё девять минут, то есть 11 МБ/с по сжатому входу.  Диск
# (8166 МБ/с NVMe) тут ни при чём — упирается в единственный поток gzip.
UNPACK_MBPS = 11.0

# ------------------------------------------------------------- мимо docker
# uv и hf открывают десятки соединений и насыщают канал целиком.  Замер:
# машина с заявленными 639 Мбит/с приняла ~7 ГБ за 82 с ≈ 700 Мбит/с.
# Ставим 0.85 — с запасом на машины, где заявленное завышено.
#
# Распаковка колёс здесь отдельно не считается: uv разжимает их на всех
# ядрах параллельно с выкачиванием, и в те же 82 секунды она уложилась.
PAYLOAD_EFFICIENCY = 0.85

BOOT_SECONDS = 95.0            # аренда -> ssh: vast достраивает образ своим ssh


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
             payload_gb: float = 0.0,
             docker_efficiency: float = DOCKER_EFFICIENCY,
             payload_efficiency: float = PAYLOAD_EFFICIENCY) -> Estimate:
    down = max(float(offer.get("inet_down") or 100), 50.0)

    img_mbps = min(down * docker_efficiency, DOCKER_CEILING_MBPS)
    image_s = image_gb * 8 * 1024 / img_mbps + image_gb * 1024 / UNPACK_MBPS
    payload_s = payload_gb * 8 * 1024 / (down * payload_efficiency)

    setup_s = BOOT_SECONDS + image_s + payload_s
    compute_s = minutes * 60
    rent = float(offer["dph_total"]) * (setup_s + compute_s) / 3600

    # `internet_down_cost_per_tb` — цена за терабайт; байты едут один раз.
    per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
    traffic = (image_gb + payload_gb) / 1024 * per_tb
    return Estimate(setup_s, compute_s, rent, traffic)


def rank(offers: list[dict], image_gb: float, minutes: float,
         payload_gb: float = 0.0, **kw) -> list[dict]:
    """Офферы по возрастанию полной стоимости прогона, с полем `_est`."""
    out = []
    for o in offers:
        e = estimate(o, image_gb, minutes, payload_gb, **kw)
        out.append({**o, "_est": e})
    return sorted(out, key=lambda o: o["_est"].total_usd)


def describe(offer: dict) -> str:
    e = offer["_est"]
    # .get(k, 0) не спасает: ключ есть, а значение None — формат падает.
    down = float(offer.get("inet_down") or 0)
    disk = float(offer.get("disk_bw") or 0)
    return (f"#{offer['id']}  ${offer['dph_total']:.3f}/час  "
            f"{down:.0f} Мбит  "
            f"{disk:.0f} МБ/с диск  "
            f"${float(offer.get('internet_down_cost_per_tb') or 0):.1f}/ТБ  "
            f"старт~{e.setup_s/60:.1f}мин  "
            f"=> ${e.total_usd:.3f} (аренда {e.rent_usd:.3f} + трафик {e.traffic_usd:.3f})  "
            f"машина {offer.get('machine_id')}")
