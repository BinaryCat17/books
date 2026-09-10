"""What a run really costs, and which offer to take.

Ranking by $/hour is wrong for two reasons. A cold start costs money and runs
over two channels an order of magnitude apart: the image through docker,
everything else past it. And inbound traffic is charged on every offer -- $0.4
to $29.3 per TB, median $2.7 over 41 of them -- so on an expensive host
delivering the environment costs more than the work does.
"""
from dataclasses import dataclass

# ------------------------------------------------------------ through docker
# One HTTP connection inside a layer and a registry capping it near 25 Mbit/s:
# 6.02 GB in 10.7 minutes on a 1518 Mbit/s link, five per cent of it.
DOCKER_EFFICIENCY = 0.05
DOCKER_CEILING_MBPS = 120.0

# Unpacking: gzip inside a layer is single-threaded and layers apply strictly
# one after another -- 11 MB/s of compressed input, whatever the disk can do.
UNPACK_MBPS = 11.0

# --------------------------------------------------------------- past docker
# uv and hf open dozens of connections and saturate the link: ~7 GB in 82 s
# where 639 Mbit/s was advertised, wheels unpacked inside the same time. The
# margin leaves room for a host whose advertised figure is optimistic.
PAYLOAD_EFFICIENCY = 0.85

BOOT_SECONDS = 95.0            # rent -> ssh: vast adds its own ssh to the image

# -------------------------------------------------------------------- warmup
# Bringing vLLM up is imports, torch.compile and a model warmup: processor work,
# not card work, and the spread between hosts is sixfold -- 65 s at 5.0 GHz
# against 374 s at a lower clock. The model is crude and inverse in the clock,
# so it belongs in the ranking and not in a filter: a faster processor is a
# trade of about $0.06/hour against up to five minutes of start.
WARMUP_REF_GHZ = 5.0           # the clock the figure above was measured at


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
             payload_gb: float = 0.0, warmup_s: float = 0.0,
             docker_efficiency: float = DOCKER_EFFICIENCY,
             payload_efficiency: float = PAYLOAD_EFFICIENCY) -> Estimate:
    down = max(float(offer.get("inet_down") or 100), 50.0)

    img_mbps = min(down * docker_efficiency, DOCKER_CEILING_MBPS)
    image_s = image_gb * 8 * 1024 / img_mbps + image_gb * 1024 / UNPACK_MBPS
    payload_s = payload_gb * 8 * 1024 / (down * payload_efficiency)

    ghz = float(offer.get("cpu_ghz") or 0) or WARMUP_REF_GHZ
    warm_s = warmup_s * WARMUP_REF_GHZ / max(ghz, 1.5)

    setup_s = BOOT_SECONDS + image_s + payload_s + warm_s
    compute_s = minutes * 60
    rent = float(offer["dph_total"]) * (setup_s + compute_s) / 3600

    # `internet_down_cost_per_tb` is per terabyte; the bytes travel once.
    per_tb = float(offer.get("internet_down_cost_per_tb") or 0)
    traffic = (image_gb + payload_gb) / 1024 * per_tb
    return Estimate(setup_s, compute_s, rent, traffic)


def rank(offers: list[dict], image_gb: float, minutes: float,
         payload_gb: float = 0.0, warmup_s: float = 0.0, **kw) -> list[dict]:
    """Offers by ascending full cost of the run, each with an `_est` field."""
    out = []
    for o in offers:
        e = estimate(o, image_gb, minutes, payload_gb, warmup_s, **kw)
        out.append({**o, "_est": e})
    return sorted(out, key=lambda o: o["_est"].total_usd)


def describe(offer: dict) -> str:
    e = offer["_est"]
    # `.get(k, 0)` does not save us: the key exists with the value None.
    down = float(offer.get("inet_down") or 0)
    disk = float(offer.get("disk_bw") or 0)
    return (f"#{offer['id']}  ${offer['dph_total']:.3f}/hour  "
            f"{down:.0f} Mbit  "
            f"{disk:.0f} MB/s disk  "
            f"{float(offer.get('cpu_ghz') or 0):.1f}GHz  "
            f"${float(offer.get('internet_down_cost_per_tb') or 0):.1f}/TB  "
            f"start~{e.setup_s/60:.1f}min  "
            f"=> ${e.total_usd:.3f} (rent {e.rent_usd:.3f} + traffic "
            f"{e.traffic_usd:.3f})  "
            f"machine {offer.get('machine_id')}")
