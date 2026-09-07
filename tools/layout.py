"""Is every book directory in the declared shape. The declaration is
`booksmith.tree.layout`, so the mutation battery can reach it.

    python3 tools/layout.py
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from booksmith.tree import layout  # noqa: E402

if __name__ == "__main__":
    sys.exit(layout.main(sys.argv[1:]))
