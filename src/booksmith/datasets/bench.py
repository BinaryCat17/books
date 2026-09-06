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

from booksmith.core import policy
from booksmith.core.errors import Unmeasurable
from booksmith.core import page

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
    def vocabulary(self) -> str | None:
        return (self.snapshot.get("policy") or {}).get("vocabulary")

    @property
    def derived_from(self) -> str | None:
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

    @property
    def pdf(self) -> str | None:
        name = self.manifest.get("pdf") or f"{self.name}.pdf"
        p = os.path.join(self.root, name)
        return p if os.path.isfile(p) else None

    @property
    def sha256(self) -> str | None:
        return self.manifest.get("sha256 pdf")

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

    def run(self, label: str = "detect") -> Run:
        """A run stored under the bench: today `<root>/<label>/`; the plan's
        step 3b makes it `<root>/detect/<label>/`."""
        return Run.open(os.path.join(self.root, label), f"run {label} of {self.name}")

    def runs(self) -> list:
        """Labels of every run under the bench root."""
        out = []
        for name in sorted(os.listdir(self.root)):
            d = os.path.join(self.root, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "run.json")) \
                    and os.path.isdir(os.path.join(d, "pages")):
                out.append(name)
        return out


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


def vocabulary_of(run: Run) -> str | None:
    """The label vocabulary a run's snapshot declares, or None."""
    v = run.vocabulary
    return v if v in policy.POLICIES else None
