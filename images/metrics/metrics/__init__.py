"""The metrics, each with its declaration and its probes"""

from metrics.assembly import AssemblyMetric
from metrics.contour import ContourMetric
from metrics.errors import Refusal
from metrics.fitness import FitnessMetric
from metrics.reading import ReadingMetric
from metrics.text import TextMetric

METRICS = (ContourMetric(), FitnessMetric(), TextMetric(), AssemblyMetric(), ReadingMetric())
BY_NAME = {m.name: m for m in METRICS}


def specs() -> dict:
    out = {}
    for m in METRICS:
        for sp in m.scalars:
            if sp.name in out:
                raise Refusal(f"scalar `{sp.name}` is declared by two metrics")
            out[sp.name] = sp
    return out


def catalog() -> list[dict]:
    return [
        {
            "metric": m.name,
            "needs": sorted(m.needs),
            "description": (type(m).__doc__ or "").strip().split("\n")[0],
            "scalars": [
                {"name": s.name, "better": s.better, "gloss": s.gloss, "question": s.question,
                 "per": s.per, "side": s.side, "unit": s.unit}
                for s in m.scalars
            ],
        }
        for m in METRICS
    ]
