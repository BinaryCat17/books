"""The registered metrics, in the order the table prints them."""
from booksmith.datasets.metrics import base  # noqa: F401
from booksmith.datasets.metrics.assembly import AssemblyMetric
from booksmith.datasets.metrics.contour import ContourMetric
from booksmith.datasets.metrics.fitness import FitnessMetric
from booksmith.datasets.metrics.snapshot import SnapshotMetric
from booksmith.datasets.metrics.text import TextMetric

METRICS = (ContourMetric(), FitnessMetric(), TextMetric(), AssemblyMetric(),
           SnapshotMetric())
BY_NAME = {m.name: m for m in METRICS}
