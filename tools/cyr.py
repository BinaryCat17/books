"""Command for the Cyrillic ratchet. The counting itself is `booksmith.cyr`.

Split so the mutation battery can break the counter: it reaches modules by
importing them, and `tools/` is not a package.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from booksmith import cyr                                   # noqa: E402

if __name__ == "__main__":
    sys.exit(cyr.main(sys.argv[1:]))
