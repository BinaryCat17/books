"""Свод проходов в одну книгу — тонкая обёртка над booksmith.merge.

    python tools/merge3.py processed/book-pass1 processed/book-pass2 \
                           processed/book-pass3 processed/book-final
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from booksmith.merge import merge

if __name__ == "__main__":
    sys.exit(merge(sys.argv[1:-1], sys.argv[-1]))
