"""What a run really costs, and which offer to take"""

from dataclasses import dataclass

DOCKER_EFFICIENCY = 0.05
DOCKER_CEILING_MBPS = 120.0
UNPACK_MBPS = 11.0
PAYLOAD_EFFICIENCY = 0.85
BOOT_SECONDS = 95.0
WARMUP_REF_GHZ = 5.0


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


def estimate(
    offer: dict,
    image_gb: float,
    minutes: float,
    payload_gb: float = 0.0,
    warmup_s: float = 0.0,
    docker_efficiency: float = DOCKER_EFFICIENCY,
    payload_efficiency: float = PAYLOAD_EFFICIENCY,
) -> Estimate:
    down = max(float(offer.get("inet_down") or 100), 50.0)
    img_mbps = min(down * docker_efficiency, DOCKER_CEILING_MBPS)
    image_s = image_gb * 8 * 1024 / img_mbps + image_gb * 1024 / UNPACK_MBPS
    payload_s = payload_gb * 8 * 1024 / (down * payload_efficiency)
    ghz = float(offer.get("cpu_ghz") or 0) or WARMUP_REF_GHZ
    warm_s = warmup_s * WARMUP_REF_GHZ / max(ghz, 1.5)
    setup_s = BOOT_SECONDS + image_s + payload_s + warm_s
    compute_s = minutes * 60
    rent = float(offer["dph_total"]) * (setup_s + compute_s) / 3600
    per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
    traffic = (image_gb + payload_gb) / 1024 * per_tb
    return Estimate(setup_s, compute_s, rent, traffic)


def rank(
    offers: list[dict],
    image_gb: float,
    minutes: float,
    payload_gb: float = 0.0,
    warmup_s: float = 0.0,
    **kw,
) -> list[dict]:
    out = []
    for o in offers:
        e = estimate(o, image_gb, minutes, payload_gb, warmup_s, **kw)
        out.append({**o, "_est": e})
    return sorted(out, key=lambda o: o["_est"].total_usd)


def describe(offer: dict) -> str:
    e = offer["_est"]
    down = float(offer.get("inet_down") or 0)
    disk = float(offer.get("disk_bw") or 0)
    return f"#{offer['id']}  ${offer['dph_total']:.3f}/hour  {down:.0f} Mbit  {disk:.0f} MB/s disk  {float(offer.get('cpu_ghz') or 0):.1f}GHz  ${float(offer.get('internet_down_cost_per_tb') or 0):.1f}/TB  start~{e.setup_s / 60:.1f}min  => ${e.total_usd:.3f} (rent {e.rent_usd:.3f} + traffic {e.traffic_usd:.3f})  machine {offer.get('machine_id')}"
