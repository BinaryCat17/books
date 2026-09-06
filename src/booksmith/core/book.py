"""THE BOOK DIRECTORY: where its parts live, asked by everyone.

The build root holds exactly one file, `book.html`; everything else is
kitchen under `assets/`. Three modules used to know the layout by their own
copy (the builder, the swap layer, the snapshot checker) and one of them
lied on the one layout it was needed for; now they ask here. `Book.open`
and the run labels arrive in step 3b of the plan.
"""
import os

# THE BOOK'S KITCHEN. The build root holds EXACTLY ONE file, `book.html`, and it
# is self-contained; crops, the observed, the snapshot and the swap journal move
# here. Not tidiness: the book is opened by double-click, and a root with four
# json files and a two-megabyte js makes the reader choose what to open. Crops
# stay files EVEN WHEN inlined (`HTML_IMAGES=inline`): edits, measurements and
# the second level need them, not just reading.
ASSETS = "assets"
SOURCE = os.path.join(ASSETS, "source")
JOURNAL = os.path.join(ASSETS, "swaps.json")


def journal_path(out_dir: str) -> str:
    """Where THIS book's swap journal lives -- one rule, asked by everyone.

    The journal moved into `assets/`, and books built before the move keep it
    in the root; `doc/apply` reads and writes the old place when it is the
    only one there. The rebuild guard in `build` did NOT: it looked only under
    `assets/`, so rebuilding into an old-layout book wiped the book while a
    live journal survived and began to lie -- the exact accident the guard
    exists to prevent, passing it by on the one layout it was needed for.

    So the rule lives here, in the lower of the two modules, and both callers
    ask it. Returns the new place when neither exists: that is where a journal
    would be created.
    """
    new = os.path.join(out_dir, JOURNAL)
    old = os.path.join(out_dir, "swaps.json")
    if not os.path.exists(new) and os.path.exists(old):
        return old
    return new
