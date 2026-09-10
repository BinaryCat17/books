class BooksmithError(Exception):
    pass


class Refusal(BooksmithError):
    pass


class Unmeasurable(BooksmithError):
    pass


class Cancelled(BooksmithError):
    pass


class TextError(Unmeasurable):
    pass
