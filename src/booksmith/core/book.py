"""The book directory: where its parts live, asked by everyone.

One directory per book, and a bench is a book that also has `truth/`.
`manifest.json` is what makes a directory a book, and `ALLOWED` below declares
the whole shape. The build root holds exactly one file, `book.html`; everything
else is kitchen under `assets/`.

A run's label is the model's own name (`Detector.label`), so two models measured
on one book do not overwrite each other. `run.json` carries `identity`, and a
command about to write a different one under an existing label refuses.
"""
from __future__ import annotations

import builtins
import os
import re
import json

from booksmith.core.log import log
from booksmith.core import config
from booksmith.core.errors import Refusal

# Crops stay files even when inlined: edits, measurements and level two need them.
ASSETS = "assets"
SOURCE = os.path.join(ASSETS, "source")
JOURNAL = os.path.join(ASSETS, "swaps.json")


def journal_path(out_dir: str) -> str:
    """Where this book's swap journal lives; one rule, asked by everyone."""
    return os.path.join(out_dir, JOURNAL)


# A run label is a directory name, and the model's name, never the adapter's:
# `doclayout-onnx` serves three models, which under one label look like one run.
LABEL_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")

# ---------------------------------------------------------------- the shape
# What a book directory holds; `tests/contract/test_book_shape.py` walks the
# roots against it, so a stray directory has a name or is a failure.

# Both roots are the same shape on purpose: a bench is a book with truth.
BOOK_ROOTS = ("bench", "processed")


def store_of(book_dir: str) -> str:
    """The store a book lies in: the directory above its `bench/` or
    `processed/`; the repository root for a book that lies in neither."""
    parent = os.path.dirname(os.path.abspath(book_dir.rstrip("/")))
    return os.path.dirname(parent) if os.path.basename(parent) in BOOK_ROOTS else config.ROOT

# A name is either exact or a pattern; `<model>` is what `safe_label` allows.
ALLOWED = (
    "manifest.json",          # what makes a directory a book
    "<source>.pdf",           # THE scan -- the one the manifest names
    "truth/",                 # a bench has one
    "detect/<model>/",        # level one, one directory per model
    "read/<model>/",          # level two
    "look/<model>.pdf",       # boxes over the pages, for the eye
    "look/truth.pdf",         # ... and truth drawn with no model beside it
    "assets/",                # the kitchen of a built book
    "book.html",              # ... and its one file
)

# What `books crop` and `books read` write beside a run. Declared because they
# sit inside `detect/`, where a name is otherwise a model's.
BESIDE_A_RUN = (".crop", ".read")

# What a run directory holds, per level. Two sets and not a union, which would
# let `read_with.json` sit under a detect run as a level-two file at level one.
INSIDE_A_RUN = {
    "detect": ("pages", "run.json"),
    # `vllm.*` come back from the card by name.
    "read": ("pages", "answers", "crops", "html", "run.json",
             "read_with.json", "job.log", "job", "vllm.json", "vllm.log"),
}

# Files a root may hold that are not books. A root is for books.
ROOT_FILES = ()


def safe_label(name: str, what: str) -> str:
    """The label, or a Refusal naming what to pass instead.

    Refused, never sanitised: two names differing only where a sanitiser bites
    would land in one directory, the second reading as a resume of the first.
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


# The two kinds of run a book holds; not a free string, or `runs()` looks in nothing.
KINDS = ("detect", "read")


class Book:
    """A book directory. `Bench` is this plus `truth/`.

    `manifest.json` is what makes a directory a book: `tests/expected/` and
    `results/` are not books, there being nothing to say which PDF they are about.
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
    def list(cls, root: str) -> builtins.list[str]:
        """Every book directory under `root`, as paths relative to it.

        A book is a directory with a manifest. `os.listdir`, not `glob("*")`,
        which skips a dotted name and would walk past a bench called `.old`.
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
        """The scan, by name beside the manifest, never by a stored path.

        The manifest is tracked and the PDF is not, so an absolute path in it
        would be false on any other machine; `run.json` records the path used.
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

    def runs(self, kind: str) -> builtins.list[str]:
        """Labels of the runs of one kind, sorted.

        A directory without `run.json` is not a run and is not listed: half a run
        counted as one is a measurement against a page set nobody snapshotted.
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
        """The directory of the run of this kind, or a Refusal that lists the
        labels. Zero and several are different failures, and are said differently.
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
    """Refuse to write a different experiment under an existing label.

    A page selector is refused too, the identity being blind to one, and so is a
    snapshot that records no identity at all -- "I cannot tell" is not "the same".

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
# A command takes a run directory or its `pages/`; these say which was given,
# and refuse naming both places looked.

def page_files(d: str) -> tuple[int, str]:
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


def pages_dir(path: str, what: str) -> str:
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


def run_dir(path: str, what: str) -> str:
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


def home_for(detect_dir: str, store: str) -> str:
    """Where the book lands BY DEFAULT: the store's `processed/`, not beside the run."""
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    stem = os.path.splitext(os.path.basename(snap["source"]["path"]))[0]
    safe = re.sub(r"[^\w.,()-]+", "-", stem, flags=re.UNICODE).strip("-")[:80]
    return os.path.join(store, "processed", safe or "book")
