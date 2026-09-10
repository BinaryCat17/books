"""One family of errors, so the command line answers every trouble alike.

`Refusal` is the run that cannot start or continue for a reason the message
names -- a missing file, an empty page set, a knob outside its range: exit
code 1, one line, no traceback. `Unmeasurable` is the instrument that could
not count: exit code 2, so that "the instrument did not run" and "the number
failed" stay two different zeros. Both are `Exception`s, not
`BaseException`s, so `except Exception` in the batteries and on the rented box
keeps catching them. Per-module classes (`MetricError`, `SynthError`, ...)
subclass one of the two and stay in their modules.
"""


class BooksmithError(Exception):
    """The base: every error this package raises on purpose."""


class Refusal(BooksmithError):
    """The run cannot go on, and the message says why. rc 1, one line."""


class Unmeasurable(BooksmithError):
    """An instrument could not count. rc 2, distinct from a number that failed."""


class WeightsMissing(Unmeasurable):
    """Weights are missing, incomplete, or would give plausible shifted boxes.

    Not a refusal: the adapter is a library, and the bench catches this like
    any other trouble instead of dying with the process.
    """


class TextError(Unmeasurable):
    """The reading metric could not count: no pages, an undeclared
    normalisation level, a truth it cannot pair. Here and not in the metric
    because `core.textnorm` raises it too and core imports nothing above itself.
    """
