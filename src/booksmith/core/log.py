"""One log line, one place. Timestamped, to stdout, flushed.

Stdout and not stderr: the acceptance snapshots (`tests/expected/*.txt`) are
the concatenation of both streams compared line by line, so a diagnostic on
stderr would reorder every report.

Import-free: `books ledger` rents nothing and must not pull in the `vastai`
package. The two entrypoints that run on the rented box keep a copy of these
two lines, because they start before the package is on `sys.path`.
"""
import time


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)
