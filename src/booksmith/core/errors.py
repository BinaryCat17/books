"""One family of errors, so the command line answers every trouble alike.

Two kinds, told apart by what the operator should do next:

* `Refusal` -- the run cannot start or continue for a reason the message
  names: a missing file, an empty page set, a knob outside its range, a
  book that is not the one the snapshot names. Exit code 1, ONE LINE, no
  traceback. Library code raises it where it used to raise
  `SystemExit("...")`; a `SystemExit` in a library forced every caller to
  special-case a `BaseException`, and a rented box that caught `Exception`
  let one through to the ledger as a free success.
* `Unmeasurable` -- an instrument could not count: weights missing, a
  label outside every vocabulary, a truth directory with no pages. Exit
  code 2, so that "the instrument did not run" and "the number failed" stay
  two different zeros.

Both are `Exception`s, not `BaseException`s: `except Exception` in the
batteries and on the box keeps catching them, which is the point.

Per-module classes (`MetricError`, `SynthError`, ...) subclass one of the
two and stay in their modules, where the battery patches them.
"""


class BooksmithError(Exception):
    """The base: every error this package raises on purpose."""


class Refusal(BooksmithError):
    """The run cannot go on, and the message says why. rc 1, one line."""


class Unmeasurable(BooksmithError):
    """An instrument could not count. rc 2, distinct from a number that failed."""


class WeightsMissing(Unmeasurable):
    """Weights are missing, incomplete, or would give plausible shifted boxes.

    Not a refusal: the adapter is a library, and the bench must catch this
    like any other trouble instead of dying with the process. Once there
    were three of these, one per adapter, and the command line listed all
    three by module path to map them to exit code 2.
    """
