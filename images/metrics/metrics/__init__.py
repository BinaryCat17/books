from metrics.assembly import AssemblyMetric
from metrics.contour import ContourMetric
from metrics.fitness import FitnessMetric
from metrics.reading import ReadingMetric
from metrics.text import TextMetric

METRICS = (ContourMetric(), FitnessMetric(), TextMetric(), AssemblyMetric(), ReadingMetric())
BY_NAME = {m.name: m for m in METRICS}


def catalog() -> list[dict]:
    return [
        {
            "metric": m.name,
            "version": m.version,
            "needs": sorted(m.needs),
            "description": m.description,
            "scalars": [
                {
                    "name": s.name,
                    "better": s.better,
                    "gloss": s.gloss,
                    "question": s.question,
                    "per": s.per,
                    "side": s.side,
                    "unit": s.unit,
                }
                for s in m.scalars
            ],
        }
        for m in METRICS
    ]
