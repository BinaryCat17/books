"""The registered metrics, in the order the table prints them."""
from booksmith.datasets.metrics.base import Metric, Record, Scalar, applicable  # noqa: F401
from booksmith.datasets.metrics.contour import ContourMetric
from booksmith.datasets.metrics.fitness import FitnessMetric
from booksmith.datasets.metrics.text import TextMetric

METRICS = (ContourMetric(), FitnessMetric(), TextMetric())
BY_NAME = {m.name: m for m in METRICS}
