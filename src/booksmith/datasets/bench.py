"""A bench and a run over it: THE loader, THE identity check.

One `Bench`, one `Run`, one `load_pages`, one `same_book`; a trait the file does
not name is "not said", counted apart from "yes" and "no". A run is a directory
of `pages/*.json` beside its `run.json`, and the snapshot is required by
`Run.open`, or the same-book check has nothing to check with. `Run.bare` takes a
page directory with no snapshot -- truth against itself, a probe's spoiled
copy -- and SAYS it is bare.
"""
import json
import os
from dataclasses import dataclass, field

from booksmith.core.errors import Unmeasurable
from booksmith.core import book as book_mod
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
    """Where a truthless book's scan is, verified, or "" if there is none:
    beside the book and in `raw/`, with the sha256 checked on BOTH branches.
    `source.name` is a file name and not a path, confined rather than trusted."""
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
                 os.path.join(book_mod.store_of(path), "raw", name)):
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
        """Which level this run is of -- `detect`, `read`, or "" outside the
        book layout -- taken from the directory it sits in. A detector and a
        reader can share a label, and only the kind keeps their files apart."""
        if not self.run_dir:
            return ""
        k = os.path.basename(os.path.dirname(os.path.abspath(self.run_dir)))
        return k if k in book_mod.KINDS else ""

    @property
    def level(self) -> str:
        """The results table's kind column: `detect`, `read`, or `hybrid` for
        a read run whose boxes are its own (`run.json` says `layout: own`)."""
        return "hybrid" if self.snapshot.get("layout") == "own" else self.kind

    @property
    def vocabulary(self) -> str | None:
        return (self.snapshot.get("policy") or {}).get("vocabulary")

    @property
    def derived_from(self) -> str | None:
        """The raw run a corrected run `read/<label>+cN/` came from. WRITTEN BY
        NOTHING YET: read here so the shape exists before the writer does."""
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
    # The scan when it had to be found: empty for a bench, whose `pdf` resolves
    # it on demand; set by `no_truth`, so that `pdf` stays total.
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
        `truth.previous` beside a rebuilt bench. The identity check says NOT
        CHECKED, as it does for a bare run; the probes take it."""
        truth_dir = truth_dir.rstrip("/")
        return cls(os.path.dirname(truth_dir) or ".", os.path.basename(truth_dir), truth_dir, {})

    @classmethod
    def no_truth(cls, path: str) -> "Bench":
        """A book directory with NO truth -- `processed/<book>` -- so that the
        truth-free metrics reach it. `truth_dir` stays empty, so `applicable`
        withholds every metric that needs truth; `open` still refuses this."""
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
        """The scan, or None. TOTAL BY CONSTRUCTION: `applicable` asks it before
        deciding anything, so a raise here would abort a whole table. Where a
        scan has to be found, the search happens once, in `_scan_of`."""
        # A truthless book answers from `scan` and nowhere else, empty or not:
        # the lazy branch below would be an unverified twin of `_scan_of`.
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
        """The run of this kind, or the one named. "The" run is defined only
        where a book holds one: `one_run` refuses zero and several apart, and
        lists the labels."""
        d = self.book().one_run(kind, label)
        return Run.open(d, f"{kind} run {label or os.path.basename(d)} "
                           f"of {self.name}")

    def runs(self, kind: str = "detect") -> list:
        """Labels of every run of one kind under the bench."""
        return self.book().runs(kind)


def same_book(bench: Bench, run: Run) -> str:
    """Are truth and run about the same PDF, by sha256 and never by directory
    name; a mismatch is `Unmeasurable`. The three phrasings stay apart:
    "checked", "not checked: no snapshot", "not checked: no field"."""
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

