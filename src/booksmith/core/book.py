"""THE BOOK DIRECTORY: where its parts live, asked by everyone.

The build root holds exactly one file, `book.html`; everything else is
kitchen under `assets/`. Three modules used to know the layout by their own
copy (the builder, the swap layer, the snapshot checker) and one of them
lied on the one layout it was needed for; now they ask here. `Book.open`
and the run labels arrive in step 3b of the plan.
"""
import os
import re

from booksmith.core.errors import Refusal

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
    in the root; `assemble/apply` reads and writes the old place when it is the
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


# A RUN LABEL IS A DIRECTORY NAME, and it is the model's name, never the
# adapter's: `doclayout-onnx` is one adapter serving three models, and three
# models under one directory look like one run resumed three times.
LABEL_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def safe_label(name: str, what: str) -> str:
    """The label, or a Refusal naming what to pass instead.

    REFUSED, NEVER SANITISED. Two models whose names differ only where the
    sanitiser bites -- a slash, a space -- would land in ONE directory, and
    the second would read as a resume of the first: same label, other
    weights, and the snapshot of the first still in place. A refusal costs a
    typed `--run`; the silent version costs a measurement nobody can trust.
    """
    name = (name or "").strip()
    if not LABEL_OK.match(name):
        raise Refusal(
            f"{what}: {name!r} cannot be a run directory name. A label is "
            f"the MODEL's name, letters, digits and . _ + - only. This one "
            f"comes from the model itself (the weights' own name, the "
            f"variant, the weights file), so a name like this means the "
            f"weights do not declare one -- pass --run <name> and the run is "
            f"filed under that.")
    return name
