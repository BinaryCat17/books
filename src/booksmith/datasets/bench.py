"""A bench and a run over it: THE loader, THE identity check.

Six places used to parse the same directory each in its own way -- the
contour metric, the reading metric, the command line's page finder, the
distillate, the overlay, and the ink metric borrowing the first -- and three
of them checked "is this the same book" by their own rule. Two of the six
defaulted a truth trait to "yes" where the file said nothing. So: one
`Bench`, one `Run`, one `load_pages`, one `same_book`, and a trait that the
file does not name is "not said", counted apart from "yes" and "no".

WHAT A RUN IS. A directory of `pages/*.json` beside its `run.json`. The
snapshot is required by `Run.open`: a bare page directory can be scored,
but then the same-book check has nothing to check with, and a page set
written by a correction must never be measured under the raw run's name.
`Run.bare` exists for the two cases where there is honestly no snapshot --
truth scored against itself, and the batteries feeding spoiled pages from a
temporary directory -- and it SAYS it is bare.
"""
import json
import os
from dataclasses import dataclass, field

from booksmith.core.errors import Unmeasurable
from booksmith.core import book as book_mod
from booksmith.core import config
from booksmith.core import page
from booksmith.core import stamp

TRAITS = ("order_marked", "text_marked")
TRAIT_STATES = ("yes", "no", "not_said")


def trait_state(meta: dict, key: str) -> str:
    """Three answers, not two. A page where the trait is absent asserts
    nothing, and a metric must stay silent over it rather than count."""
    if key not in (meta or {}):
        return "not_said"
    return "yes" if meta[key] else "no"


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _scan_of(path: str, man: dict, sha: str) -> str:
    """Where a truthless book's scan is, verified, or "" if there is none.

    CLAUDE.md: "The only thing not inside is the source PDF" -- a built book
    keeps its scan in `raw/`, so looking only beside the book left the ink
    half silently inapplicable on every one of them.

    THE SHA IS CHECKED ON BOTH BRANCHES. The first edition checked only the
    `raw/` one and said in this very docstring that it checked "here and
    nowhere else" -- so a `book.pdf` sitting beside the manifest was handed
    to `ink.measure` unverified, and the guard bit only in the rarer layout.
    A file whose bytes are not the ones the manifest names produces exactly
    the "looks sensible and means nothing" number this function exists to
    prevent, and where it lies makes no difference to that.

    `source.name` IS A FILENAME, NOT A PATH. It is data, and it decides what
    gets opened and hashed, so it is confined rather than trusted: an
    absolute name made `os.path.join(path, name)` return the name itself
    (`/etc/hosts` resolved, existed, and came back before the sha branch was
    ever reached), and `../../..` walked out of the repository and was
    accepted whenever the manifest's own sha matched the file it pointed at
    -- the author of the manifest controls both halves of that comparison.

    THE SEARCH IS CONFINED TO `no_truth`. `raw/` is keyed by FILENAME under
    the REPOSITORY root, not under the book, so letting every `Bench`
    anywhere consult it made a fixture manifest naming `book.pdf` resolve to
    whatever the developer happened to have there: two planted files turned
    four checks red, and one of them was the check added for this feature.
    """
    name = (man.get("source") or {}).get("name") or ""
    if not name:
        return ""
    if name != os.path.basename(name) or name in (os.curdir, os.pardir):
        raise Unmeasurable(
            f"{os.path.basename(path)}/manifest.json names a source of "
            f"{name!r}, which is a path and not a file name. The scan is "
            f"looked up beside the book and in raw/, by name; a manifest "
            f"that steers that lookup elsewhere is a defect, not a lookup.")
    for cand in (os.path.join(path, name),
                 os.path.join(config.ROOT, "raw", name)):
        if not os.path.isfile(cand):
            continue
        got = stamp.sha256(cand)
        if got != sha:
            raise Unmeasurable(
                f"{cand} is not the scan {os.path.basename(path)} is about: "
                f"manifest.json says sha256 {sha[:12]}, the file is "
                f"{got[:12]}. Two scans share a name; measuring this one "
                f"would look sensible and mean nothing.")
        return cand
    return ""


@dataclass
class Run:
    """A pages directory and the snapshot it was written with."""
    pages_dir: str
    run_dir: str | None
    snapshot: dict = field(default_factory=dict)
    label: str = ""

    @classmethod
    def open(cls, path: str, what: str = "run") -> "Run":
        """The run at `path`: its directory (holding `run.json` and
        `pages/`) or its `pages/` directory itself. Refuses a bare one."""
        path = path.rstrip("/")
        if not os.path.exists(path):
            raise Unmeasurable(f"{what}: no path {path}")
        for run_dir, pages in ((path, os.path.join(path, "pages")),
                               (os.path.dirname(path), path)):
            snap = _read_json(os.path.join(run_dir, "run.json"))
            if snap is not None and os.path.isdir(pages):
                return cls(pages, run_dir, snap, os.path.basename(run_dir))
        raise Unmeasurable(
            f"{what}: {path} is not a run: expected a directory holding "
            f"run.json and pages/, or the pages/ directory of one. A page "
            f"directory without its snapshot cannot say which book or which "
            f"model it is about; `Run.bare` takes one on purpose.")

    @classmethod
    def bare(cls, pages_dir: str, label: str = "") -> "Run":
        """A page directory with no snapshot: truth against itself, or a
        battery's spoiled copy. The identity check will say NOT CHECKED."""
        return cls(pages_dir.rstrip("/"), None, {},
                   label or os.path.basename(pages_dir.rstrip("/")))

    @property
    def sha256(self) -> str | None:
        return (self.snapshot.get("source") or {}).get("sha256")

    @property
    def kind(self) -> str:
        """WHICH LEVEL this run is of -- `detect`, `read`, or "" when the
        run stands outside the book layout (a bare pages directory, a
        battery's spoiled copy).

        Taken from the directory the run sits in, because that is where the
        book layout puts it and `core.book.KINDS` declares the two names.
        It is not decoration: a run's LABEL is the model's own name, and a
        detector and a reader could share one, so without the kind two
        different measurements land on one results file and the second
        overwrites the first.
        """
        if not self.run_dir:
            return ""
        k = os.path.basename(os.path.dirname(os.path.abspath(self.run_dir)))
        return k if k in book_mod.KINDS else ""

    @property
    def vocabulary(self) -> str | None:
        return (self.snapshot.get("policy") or {}).get("vocabulary")

    @property
    def derived_from(self) -> str | None:
        """WRITTEN BY NOTHING YET. Step 4 makes it: a correction produces a
        derived run `read/<label>+cN/` whose snapshot names the raw run it
        came from. Read here so the shape exists before the writer does, and
        said so rather than looking finished."""
        return self.snapshot.get("derived_from")

    def pages(self) -> dict:
        return page.load_pages(self.pages_dir, f"run {self.label}")


@dataclass
class Bench:
    """A book directory with truth."""
    root: str
    name: str
    truth_dir: str
    manifest: dict = field(default_factory=dict)
    # THE SCAN, WHEN IT HAD TO BE FOUND. Empty for a bench, whose scan sits
    # beside its truth and is resolved by `pdf` on demand; set by `no_truth`,
    # where the scan lives in `raw/` and the search can fail. Filled at
    # construction so that `pdf` stays total -- see its docstring.
    scan: str = ""

    @classmethod
    def open(cls, path: str) -> "Bench":
        """The bench at `path`: its root (holding `truth/`) or its `truth/`."""
        path = path.rstrip("/")
        if os.path.isdir(os.path.join(path, "truth")):
            root, truth = path, os.path.join(path, "truth")
        elif os.path.basename(path) == "truth" and os.path.isdir(path):
            root, truth = os.path.dirname(path), path
        else:
            raise Unmeasurable(
                f"{path} is not a bench: expected a directory holding "
                f"truth/ (and manifest.json), or the truth/ directory itself")
        man = _read_json(os.path.join(root, "manifest.json")) or {}
        return cls(root, os.path.basename(os.path.abspath(root)), truth, man)

    @classmethod
    def bare(cls, truth_dir: str) -> "Bench":
        """A truth directory with no bench around it: a scratch copy, a
        `truth.previous` beside a rebuilt bench. The identity check says
        NOT CHECKED, as it does for a bare run. The batteries take it,
        because they need only the pages and, for the ink one, a PDF given
        by hand; the first edition of `--selfcheck` through `Bench.open`
        refused every such directory, where the same two arguments without
        `--selfcheck` measured fine."""
        truth_dir = truth_dir.rstrip("/")
        return cls(os.path.dirname(truth_dir) or ".", os.path.basename(truth_dir), truth_dir, {})

    @classmethod
    def no_truth(cls, path: str) -> "Bench":
        """A BOOK DIRECTORY WITH NO TRUTH -- `processed/<book>`.

        A bench is a book with `truth/`; this is the other half of that
        sentence, and it exists because the only two books in the tree that
        carry a LEVEL-TWO run carry no truth, so every truth-free metric --
        ink, column jumps, the snapshot -- was unreachable on exactly the
        runs it was written for. `books bench all processed/ogneupory-vl2`
        answered "is not a bench" and stopped.

        `manifest.json` WITH `source.sha256` is required, and that is the
        point rather than tidiness: the sha is the only thing `same_book` can
        check a truthless book by. Requiring merely "a manifest" was not
        enough -- `{"about": "anything"}` passed it, and a run of another
        book then measured here under a name that looked right, logging
        "sha256 not checked: the field is absent from the snapshot", the
        exact outcome this guard is for.

        A BENCH WHOSE TRUTH IS MISSING IS NOT A BOOK WITHOUT TRUTH. The two
        are indistinguishable by "is there a truth/ directory", and the
        difference is the project's own two zeros: the first is a broken
        working tree, the second is a legitimate thing to measure. An
        interrupted bench build leaves exactly the first, and without a
        refusal that bench would be measured truth-free, its record would
        overwrite the full one under the same name, and METRICS.md would
        publish "contour does not apply to atlas".

        THE TELL IS THE WRITE-ASIDE, AND IT HAS TWO HALVES. `.gitignore`
        names them in one sentence -- "`truth.new` and `truth.previous` are
        the two halves of the write-aside dance" -- and an interrupted FIRST
        build leaves `truth.new/` with neither of the others. Both are
        refused.

        WHAT IS NOT A TELL IS LIVING UNDER `bench/`. The first edition
        refused that too, and it was wrong twice over: `core.book.ALLOWED` lists
        `truth/` as an OPTIONAL part and says in its own words that "a bench
        is a book with truth, and `Book.open` does not care which tree it is
        in", and three tracked books -- `bench/real-holdout20`,
        `bench/real-tables20`, `bench/real-test25` -- say of THEMSELVES in
        their manifests "a real scan with NO TRUTH: a book, not a bench.
        Kept for measuring what needs no truth (ink, assembly order)". The
        rule made the three books this feature exists for permanently
        unreachable, and told the reader to repair a tree that was not
        broken.

        NOT a loosening of `open`. `open` still refuses a directory with no
        `truth/`, because a bench without truth is a caller's mistake and
        `tests/test_bench.py` holds it to that; this is a second door, named
        for what it opens, and `truth_dir` stays empty so `applicable`
        withholds every metric that needs truth.
        """
        path = path.rstrip("/")
        man = _read_json(os.path.join(path, "manifest.json"))
        if not man:
            raise Unmeasurable(
                f"{path} is not a book: expected manifest.json naming the "
                f"scan it is about. Without it nothing here can be checked "
                f"against the run's own snapshot.")
        sha = (man.get("source") or {}).get("sha256")
        if not sha:
            raise Unmeasurable(
                f"{path}/manifest.json names no source.sha256, so nothing "
                f"here can be checked against the run that produced it: a "
                f"run of ANOTHER book would measure clean under this name.")
        aside = [n for n in ("truth.new", "truth.previous")
                 if os.path.isdir(os.path.join(path, n))]
        if aside:
            raise Unmeasurable(
                f"{path} has {'/, '.join(aside)}/ but no truth/: this is a "
                f"bench whose build was interrupted, not a book without "
                f"truth. Measuring it truth-free would file half a record "
                f"under the full one's name. Finish the build, or remove "
                f"{' and '.join(aside)}/ if the truth is gone for good.")
        return cls(path, os.path.basename(os.path.abspath(path)), "", man,
                   _scan_of(path, man, sha))

    @property
    def pdf(self) -> str | None:
        """The scan, or None. TOTAL BY CONSTRUCTION -- it never raises.

        `applicable` asks this before deciding anything (`if bench.pdf`), so
        a raise here aborts a whole table, including metrics that need no
        PDF at all: `books bench all --only contour` died inside the ink
        question. Where a scan has to be FOUND rather than sat beside, the
        search and its refusal happen once at construction (`_scan_of`),
        where a refusal is the caller's answer rather than a surprise
        inside somebody else's `if`.
        """
        # A TRUTHLESS BOOK ANSWERS FROM `scan` AND NOWHERE ELSE, even when
        # `scan` is empty. The lazy branch below re-does the same
        # beside-the-book lookup WITHOUT hashing, so while it was reachable
        # it stood behind `_scan_of` as an unverified twin: delete the
        # verified candidate and the property still returned the file, and
        # the battery proved it -- "the scan is looked for in raw/ and not
        # beside the book" went UNCAUGHT. Two lookups of one path, one
        # checked and one not, and the unchecked one winning by fallback.
        if not self.truth_dir:
            return self.scan or None
        if self.scan:
            return self.scan
        if not self.manifest:
            return None
        name = ((self.manifest.get("source") or {}).get("name")
                or f"{self.name}.pdf")
        p = os.path.join(self.root, name)
        return p if os.path.isfile(p) else None

    @property
    def sha256(self) -> str | None:
        return (self.manifest.get("source") or {}).get("sha256")

    def pages(self) -> dict:
        return page.load_pages(self.truth_dir, f"truth of {self.name}")

    def traits(self, pages: dict | None = None) -> dict:
        """{trait: {yes, no, not_said}} counted over the truth pages."""
        pages = pages if pages is not None else self.pages()
        out = {k: {s: 0 for s in TRAIT_STATES} for k in TRAITS}
        for p in pages.values():
            for k in TRAITS:
                out[k][trait_state(p.get("meta") or {}, k)] += 1
        return out

    def has_content(self, pages: dict | None = None) -> bool:
        """Does the truth carry characters at all (a reading metric needs
        them; the golden bench annotates boxes and no text)."""
        pages = pages if pages is not None else self.pages()
        return any(b.get("content") for p in pages.values()
                   for b in p["blocks"])

    def book(self) -> book_mod.Book:
        """The bench as a book directory. A bench IS a book with `truth/`,
        and the run layout is the book's, asked in one place."""
        return book_mod.Book(self.root, self.manifest)

    def run(self, label: str = "", kind: str = "detect") -> Run:
        """THE run of this kind, or the one named.

        The default used to be the literal label `detect`, when a bench held
        exactly one run in a directory of that name. It now holds one per
        MODEL, and "the run" is only defined when there is one: `one_run`
        refuses zero and several apart, and lists the labels.
        """
        d = self.book().one_run(kind, label)
        return Run.open(d, f"{kind} run {label or os.path.basename(d)} "
                           f"of {self.name}")

    def runs(self, kind: str = "detect") -> list:
        """Labels of every run of one kind under the bench."""
        return self.book().runs(kind)


def same_book(bench: Bench, run: Run) -> str:
    """Are truth and run about the same PDF. Compared by sha256, never by
    directory name. A mismatch is `Unmeasurable`: a number here would look
    sensible and mean nothing. The three phrasings are kept apart on
    purpose ("checked", "not checked: no snapshot", "not checked: no field")
    because collapsing them was the exact loss the acceptance records were
    built to catch."""
    if run.run_dir is None or bench is None or not bench.manifest:
        return "sha256 not checked: no manifest.json or run.json beside"
    a, b = bench.sha256, run.sha256
    if not (a and b):
        return "sha256 not checked: the field is absent from the snapshot"
    if a != b:
        raise Unmeasurable(
            f"truth and model output are about DIFFERENT books: sha256 "
            f"{a[:12]} against {b[:12]}. A number here would look sensible "
            f"and mean nothing.")
    return f"sha256 checked: {a[:12]}"

