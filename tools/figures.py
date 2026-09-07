"""One measurement, one document. The instrument is `booksmith.tree.figures`,
so the mutation battery can reach it. NOT `numbers.py`: on `tools/` that name
shadows the standard library module numpy imports, and every instrument beside
it dies with "module 'numbers' has no attribute 'Integral'".

    python3 tools/figures.py           what is duplicated, and where
    python3 tools/figures.py --check   red if the count rose
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from booksmith.tree import figures  # noqa: E402

if __name__ == "__main__":
    sys.exit(figures.main(sys.argv[1:]))
