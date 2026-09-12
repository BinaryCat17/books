# The metrics image takes no settings: what it measures is decided by the run it
# is given, not by its own environment. job.Job refuses any setting against this.
KNOBS: tuple = ()
KNOB: dict = {}


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)
