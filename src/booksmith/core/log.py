"""One log line, one place. Timestamped, to STDOUT, flushed.

Stdout and not stderr on purpose: the acceptance snapshots
(`bench/expected/*.txt`) are the concatenation of both streams, and every
report is compared line by line; moving diagnostics to stderr would reorder
every one of them for no gain.

Import-free on purpose: `books ledger` is a command that rents nothing and
must not import the `vastai` package, which is why `remote/ledger.py` once
kept a `log` of its own rather than take `remote/vast.py`'s. Four copies
of these two lines are gone; the two entrypoints that run ON THE RENTED BOX
keep theirs, because they start before the package is on `sys.path`.
"""
import time


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)
