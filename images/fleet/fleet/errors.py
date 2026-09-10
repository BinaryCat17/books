class BooksmithError(Exception):
    pass


class Refusal(BooksmithError):
    pass


class Cancelled(BooksmithError):
    pass
