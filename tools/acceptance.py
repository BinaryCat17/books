"""Command for the acceptance snapshots. The table itself is
`booksmith.acceptance`, so the mutation battery can reach it.

    python3 tools/acceptance.py --save     write bench/expected/*.txt
    python3 tools/acceptance.py            diff every report against its snapshot
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from booksmith import acceptance                            # noqa: E402

if __name__ == "__main__":
    sys.exit(acceptance.main(sys.argv[1:]))
