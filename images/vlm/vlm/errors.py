"""One family of errors, so the command line answers every trouble alike"""


class BooksmithError(Exception):
    pass


class Refusal(BooksmithError):
    pass


class Unmeasurable(BooksmithError):
    pass


class Cancelled(BooksmithError):
    pass


class WeightsMissing(Unmeasurable):
    pass


class TextError(Unmeasurable):
    pass
