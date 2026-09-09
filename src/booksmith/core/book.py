"""THE BOOK DIRECTORY: where its parts live, asked by everyone.

The build root holds exactly one file, `book.html`; everything else is
kitchen under `assets/`. Three modules used to know the layout by their own
copy (the builder, the swap layer, the snapshot checker) and one of them
lied on the one layout it was needed for; now they ask here.

ONE DIRECTORY PER BOOK, and a bench is a book that also has `truth/`:

    <book>/
      manifest.json      source: {name, sha256} -- written by the first
                         command that makes the directory
      <name>.pdf         the scan (untracked for every bench we build)
      truth/             only a bench has this
      detect/<label>/    a level-one run: pages/ and run.json
      read/<label>/      a level-two run          <- NOT WRITTEN YET
      build/             the HTML and its kitchen <- NOT WRITTEN YET

THE LAST TWO ARE THE PLAN, NOT THE TREE, and saying so is the point: `books
read` still writes `<detect dir>.read` and `books html` still writes
`processed/<name>/`, and `build` has no caller outside this file.

"SO `runs("read")` IS ALWAYS EMPTY" STOOD HERE AND STOPPED BEING TRUE while
this paragraph was being edited: `processed/ogneupory-vl2` holds two level-two
runs under `read/`, moved there by hand when the book directories were given
one shape, and `runs("read")` answers with both. So the shape exists on disk
and no command writes it -- which is a third state, and worth more than the
two the sentence had room for. They were advertised here and in CLAUDE.md as
though they existed, which made 3b read as finished when a third of it is
not. Step 3c moves the two commands onto this layout.

THE LABEL IS THE MODEL'S NAME (`Detector.label`), so two models measured on
one book do not overwrite each other -- which is what "run every detector and
put the numbers side by side" needs, and what a single `detect/` could not
give. `run.json` carries `identity`, and a command about to write a DIFFERENT
identity under an existing label refuses and asks for `--run`.
"""
from __future__ import annotations

import os
import re
import json

from booksmith.core.log import log
from booksmith.core import config
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
    """Where this book's swap journal lives; one rule, asked by everyone."""
    return os.path.join(out_dir, JOURNAL)


# A RUN LABEL IS A DIRECTORY NAME, and it is the model's name, never the
# adapter's: `doclayout-onnx` is one adapter serving three models, and three
# models under one directory look like one run resumed three times.
LABEL_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")

# ---------------------------------------------------------------- the shape
# WHAT A BOOK DIRECTORY HOLDS, declared -- so "nothing outdated" is a property
# of the tree and not a tidy-up someone did once. `bench/` had drifted into
# four kinds of thing under one name, an overlay under two names and one run
# split across two sibling directories, and nothing was caught because nothing
# said what a book directory IS. `tests/contract/test_book_shape.py` walks
# `bench/` and `processed/` against this.

# Both roots are the same shape on purpose: a bench is a book with truth.
BOOK_ROOTS = ("bench", "processed")

# A name is either exact or a pattern; `<model>` is what `safe_label` allows.
ALLOWED = (
    "manifest.json",          # what makes a directory a book
    "<source>.pdf",           # THE scan -- the one the manifest names
    # A PAGE SELECTOR, AND IT HAS NO READER: the page numbers held out of one
    # real scan, 97 bytes, reconstructible by nothing. Named here so the walk
    # does not chase it, and so it is not deleted for being unread.
    "truth/",                 # a bench has one
    "detect/<model>/",        # level one, one directory per model
    "read/<model>/",          # level two
    "look/<model>.pdf",       # boxes over the pages, for the eye
    "look/truth.pdf",         # ... and truth drawn with no model beside it
    "assets/",                # the kitchen of a built book
    "book.html",              # ... and its one file
)

# What `books crop` and `books read` write BESIDE a run: `<run dir>.crop` and
# `<run dir>.read`. Declared because they sit inside `detect/`, where a name is
# otherwise a model and `LABEL_OK` matches `PP-DocLayoutV2.crop` perfectly.
BESIDE_A_RUN = (".crop", ".read")

# WHAT A RUN DIRECTORY HOLDS, per level. Two sets and not one union: a union is
# a weaker check wearing the same green, and `read_with.json` under a DETECTION
# run would mean a level-two artefact filed at level one.
INSIDE_A_RUN = {
    "detect": ("pages", "run.json"),
    # `vllm.*` and `progress.json` come back from the card by name.
    "read": ("pages", "answers", "crops", "html", "run.json",
             "read_with.json", "job.log", "job",
             "vllm.json", "vllm.log", "progress.json"),
}

# Files a root may hold that are not books. A root is for books.
ROOT_FILES = ()


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


# The two kinds of run a book holds. Not a free string: a typo would make a
# directory nobody looks in, and `runs()` would report the book as having none.
KINDS = ("detect", "read")


class Book:
    """A book directory. `Bench` is this plus `truth/`.

    `manifest.json` is what makes a directory a book. `tests/expected/` and
    `results/` are directories under `bench/` and are NOT books; without
    the manifest there is nothing to say which PDF they are about, and opening
    them would measure a page set against a book nobody named.
    """

    def __init__(self, root: str, manifest: dict):
        self.root = os.path.abspath(root.rstrip("/"))
        self.name = os.path.basename(self.root)
        self.manifest = manifest

    # ------------------------------------------------------------ opening
    @classmethod
    def open(cls, path: str, what: str = "book") -> Book:
        path = path.rstrip("/")
        man = os.path.join(path, "manifest.json")
        if not os.path.isfile(man):
            raise Refusal(
                f"{what}: {path} is not a book directory -- no manifest.json. "
                f"A book directory is made by the first command that writes "
                f"into it, and the manifest is what says WHICH PDF it is "
                f"about; without it a page set can be measured against a book "
                f"nobody named.")
        import json
        with open(man, encoding="utf-8") as f:
            return cls(path, json.load(f))

    @classmethod
    def list(cls, root: str) -> list[str]:
        """Every book directory under `root`, as paths relative to it.

        A book is a directory with a manifest. `os.listdir` and not
        `glob("*")`, which skips a dotted name: a stale bench called `.old`
        was walked by nothing at all.
        """
        out = []
        for top in BOOK_ROOTS:
            d = os.path.join(root, top)
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name)
                if os.path.isfile(os.path.join(p, "manifest.json")):
                    out.append(os.path.relpath(p, root))
        return out

    # -------------------------------------------------------------- parts
    @property
    def pdf(self) -> str | None:
        """The scan, by NAME beside the manifest -- never by a stored path.

        `Bench.pdf` is the same fact by a second rule (a `<name>.pdf` fallback
        and a relative path); the manifest key was unified and the resolvers
        were not. Harmless while every manifest carries `source.name`, and
        3c folds `Bench` onto this one.

        The manifest is tracked and the PDF is not, so an absolute path in it
        would be false on every other machine; `run.json` stores the path it
        was read at, which is the right place for it (it records what
        happened) and the wrong place to resolve from (the book moves).
        """
        name = (self.manifest.get("source") or {}).get("name")
        if not name:
            return None
        p = os.path.join(self.root, name)
        return p if os.path.isfile(p) else None

    @property
    def sha256(self) -> str | None:
        return (self.manifest.get("source") or {}).get("sha256")

    @property
    def truth_dir(self) -> str | None:
        d = os.path.join(self.root, "truth")
        return d if os.path.isdir(d) else None

    @property
    def build(self) -> str:
        return os.path.join(self.root, "build")

    def journal(self) -> str:
        return journal_path(self.build)

    # --------------------------------------------------------------- runs
    def run_dir(self, kind: str, label: str) -> str:
        if kind not in KINDS:
            raise Refusal(f"{kind!r} is not a kind of run; I know {KINDS}")
        return os.path.join(self.root, kind, safe_label(label, kind))

    def runs(self, kind: str) -> list[str]:
        """Labels of the runs of one kind, sorted. A directory without
        `run.json` is not a run and is not listed: half a run counted as one
        is how a measurement gets taken against a page set nobody snapshotted.
        """
        if kind not in KINDS:
            raise Refusal(f"{kind!r} is not a kind of run; I know {KINDS}")
        base = os.path.join(self.root, kind)
        if not os.path.isdir(base):
            return []
        return sorted(
            n for n in os.listdir(base)
            if os.path.isfile(os.path.join(base, n, "run.json"))
            and os.path.isdir(os.path.join(base, n, "pages")))

    def one_run(self, kind: str, label: str = "") -> str:
        """The directory of THE run of this kind, or a Refusal that LISTS the
        labels.

        Zero and several are different failures and are said differently. The
        old shape -- one `detect/` per book -- could not have this problem and
        could not answer "which model was that", which is the whole reason
        the labels exist.
        """
        if label:
            d = self.run_dir(kind, label)
            if not os.path.isdir(d):
                raise Refusal(
                    f"{self.name}: no {kind} run labelled {label!r}. "
                    f"There is {self._listing(kind)}")
            return d
        got = self.runs(kind)
        if len(got) == 1:
            return self.run_dir(kind, got[0])
        if not got:
            raise Refusal(
                f"{self.name} has no {kind} run at all. Make one first: "
                + (f"`books detect {self.root}`" if kind == "detect" else
                   "`books read <detect dir>` -- level two does not write "
                   "into the book directory yet, see the header"))
        raise Refusal(
            f"{self.name} has {len(got)} {kind} runs and none was named: "
            f"{', '.join(got)}. Say --run <label>; measuring \"the\" run "
            f"when there are several would file the number against whichever "
            f"sorted first.")

    def _listing(self, kind: str) -> str:
        got = self.runs(kind)
        return (", ".join(got) if got else f"no {kind} run in this book")


def guard_identity(run_dir: str, identity: str, pages_spec: str = "",
                   what: str = "this run") -> None:
    """Refuse to write a DIFFERENT experiment under an existing label.

    THE SENTENCE WAS IN TWO DOCUMENTS AND IN NO CODE. `identity` was computed
    and written and read back by nothing, so this passed in silence:

        books detect <book> --out d --pages 1                      id 2b576f4e
        LAYOUT_SCORE_THRESHOLD=0.9 books detect <book> --out d ...  id 71ffb8b2

    -- a different experiment overwriting the first, under its name and beside
    its snapshot.

    AND `--pages` IS THE SECOND HALF. The identity is over the fingerprint and
    the knobs, and a page selector is neither, so a three-page run and a
    thirteen-page run of one model hash the same. A partial run that lands on
    a whole one leaves a directory whose snapshot describes a run that never
    happened over pages that are still there from the previous one. So a
    selector is refused over an existing run outright: `--run` names a new
    label for it, and the two stand side by side, which is the whole point of
    labels.

    A run whose snapshot carries no identity at all is refused too, not
    assumed equal: those are the runs migrated from before identities existed,
    and "I cannot tell" is not "the same".
    """
    import json
    snap = os.path.join(run_dir, "run.json")
    if not os.path.isfile(snap):
        return                       # nothing there to disagree with
    try:
        with open(snap, encoding="utf-8") as f:
            was = json.load(f)
    except (OSError, ValueError) as e:
        raise Refusal(
            f"{snap} cannot be read ({type(e).__name__}), and it is what says "
            f"whether {what} is the same experiment as the one already there. "
            f"Remove the directory or give --run a new label.")
    old = was.get("identity")
    if old is None:
        raise Refusal(
            f"{run_dir} holds a run whose snapshot records no identity -- it "
            f"predates them -- so there is no telling whether {what} is the "
            f"same experiment. Give --run a new label, or remove it.")
    if old != identity:
        raise Refusal(
            f"{run_dir} holds a DIFFERENT experiment: identity {old[:12]} "
            f"against {identity[:12]}. Same model, other conditions -- a knob "
            f"the run reads, or other weights. Writing here would leave one "
            f"snapshot over two runs' pages. Give --run a new label and the "
            f"two stand side by side, which is what labels are for.")
    if pages_spec:
        raise Refusal(
            f"{run_dir} already holds a run, and --pages {pages_spec} would "
            f"write a PART of one over it. The identity cannot see a page "
            f"selector -- it is over the model and the knobs -- so the "
            f"snapshot would describe a run that never happened over pages "
            f"left from the one that did. Give --run a new label, or remove "
            f"the directory: its two sibling refusals say both and this one "
            f"said only the first, which made re-running a three-page smoke "
            f"test look forbidden.")


# ------------------------------------------------ paths a command is given ---
# A command takes a run directory or its pages/; these say which was given and
# refuse with a reason naming both places looked.

def page_files(d):
    """(how many layout pages, and if zero — why exactly)."""
    if not os.path.isdir(d):
        return 0, "not a directory"
    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".json") and f != "run.json")
    if not names:
        return 0, "no json files at all"
    try:
        with open(os.path.join(d, names[0]), encoding="utf-8") as f:
            first = json.load(f)
    except (OSError, ValueError) as e:
        return 0, f"{names[0]} does not read as json ({type(e).__name__})"
    if not (isinstance(first, dict) and "blocks" in first
            and "index" in first):
        return 0, (f"json files {len(names)}, but {names[0]} is not a layout "
                   f"page: no blocks/index fields")
    return len(names), ""


def pages_dir(path, what, log=log):
    """The PAGE directory: out of the run directory, or itself."""
    if not os.path.exists(path):
        raise Refusal(
            f"{what}: no path {path}. Expected a `books detect` run "
            f"directory (pages/ and run.json in it) or the directory of "
            f"layout pages itself (*.json).")
    sub = os.path.join(path, "pages")
    (here, why_here), (there, why_sub) = page_files(path), page_files(sub)
    if there and not here:
        log(f"{what}: given a run directory, taking the pages from {sub} — "
            f"there are {there}")
        return sub
    if here:
        return path
    raise Refusal(
        f"{what}: no layout pages found. In {path} — {why_here}; in {sub} — "
        f"{why_sub}. Expected a `books detect` run directory (pages/ and "
        f"run.json in it) or the page directory itself. There is nothing to "
        f"count — and that is not a zero of losses.")


def run_dir(path, what, log=log):
    """The RUN directory: the one holding `run.json`. Takes `<out>/pages` too."""
    if not os.path.exists(path):
        raise Refusal(
            f"{what}: no path {path}. Expected a `books detect` run "
            f"directory — the one holding run.json.")
    if os.path.exists(os.path.join(path, "run.json")):
        return path
    up = os.path.dirname(os.path.abspath(path.rstrip("/")))
    if page_files(path)[0] and os.path.exists(os.path.join(up, "run.json")):
        log(f"{what}: given a page directory, taking the snapshot from {up}")
        return up
    raise Refusal(
        f"{what}: no run.json in {path}. Expected a `books detect` run "
        f"directory (pages/ and run.json in it), not a page directory and "
        f"not a book root.")


def pdf_of(detect_dir: str) -> str:
    """The scan a detect run was taken on, as its snapshot names it."""
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)["source"]["path"]


def home_for(detect_dir: str) -> str:
    """Where the book lands BY DEFAULT: somewhere permanent, not beside the run."""
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    stem = os.path.splitext(os.path.basename(snap["source"]["path"]))[0]
    safe = re.sub(r"[^\w.,()-]+", "-", stem, flags=re.UNICODE).strip("-")[:80]
    return os.path.join(config.ROOT, "processed", safe or "book")
