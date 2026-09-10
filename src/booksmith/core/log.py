"""One line of output, one place: an event on the current job.

`log("text", page=3)` is text with fields beside it. The default sink prints
the text with a timestamp; a server's keeps the fields. The two entrypoints
that run on the rented box keep a printing copy of their own, because they
start before the package is on `sys.path`.
"""
from booksmith.core import job


def log(*a: object, **fields: object) -> None:
    job.current().sink({"text": " ".join(str(x) for x in a), **fields})
