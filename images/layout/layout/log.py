"""One line of output, one place: an event on the current job"""

from layout import job


def log(*a: object, **fields: object) -> None:
    job.current().sink({"text": " ".join(str(x) for x in a), **fields})
