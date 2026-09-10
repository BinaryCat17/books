"""A bench and a run over it: THE loader, THE identity check"""

import json
import os
from dataclasses import dataclass, field
from datasets.errors import Unmeasurable
from datasets import store as book_mod
from datasets import classes as policy_mod
from datasets import page
from datasets import identity as stamp

TRAITS = ("order_marked", "text_marked", "labelled")
TRAIT_STATES = ("yes", "no", "not_said")


def trait_state(meta: dict, key: str) -> str:
    if key not in (meta or {}):
        return "not_said"
    return "yes" if meta[key] else "no"


def labelled_of(pages: dict) -> dict:
    out = {s: 0 for s in TRAIT_STATES}
    for p in pages.values():
        out[trait_state(p.get("meta") or {}, "labelled")] += 1
    return out


def labelled_said(labelled: dict) -> bool:
    return bool(labelled["yes"] or labelled["no"])


def book_of(bench: "Bench") -> str:
    root = os.path.basename(os.path.dirname(os.path.abspath(bench.root)))
    return f"{root}/{bench.name}" if root in book_mod.BOOK_ROOTS else bench.name


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _scan_of(path: str, man: dict, sha: str) -> str:
    name = (man.get("source") or {}).get("name") or ""
    if not name:
        return ""
    if name != os.path.basename(name) or name in (os.curdir, os.pardir):
        raise Unmeasurable(
            f"{os.path.basename(path)}/manifest.json names a source of {name!r}, which is a path and not a file name. The scan is looked up beside the book and in raw/, by name; a manifest that steers that lookup elsewhere is a defect, not a lookup."
        )
    for cand in (os.path.join(path, name), os.path.join(book_mod.store_of(path), "raw", name)):
        if not os.path.isfile(cand):
            continue
        got = stamp.sha256(cand)
        if got != sha:
            raise Unmeasurable(
                f"{cand} is not the scan {os.path.basename(path)} is about: manifest.json says sha256 {sha[:12]}, the file is {got[:12]}. Two scans share a name; measuring this one would look sensible and mean nothing."
            )
        return cand
    return ""


@dataclass
class Run:
    pages_dir: str
    run_dir: str | None
    snapshot: dict = field(default_factory=dict)
    label: str = ""

    @classmethod
    def open(cls, path: str, what: str = "run") -> "Run":
        path = path.rstrip("/")
        if not os.path.exists(path):
            raise Unmeasurable(f"{what}: no path {path}")
        for run_dir, pages in ((path, os.path.join(path, "pages")), (os.path.dirname(path), path)):
            snap = read_json(os.path.join(run_dir, "run.json"))
            if snap is not None and os.path.isdir(pages):
                return cls(pages, run_dir, snap, os.path.basename(run_dir))
        raise Unmeasurable(
            f"{what}: {path} is not a run: expected a directory holding run.json and pages/, or the pages/ directory of one. A page directory without its snapshot cannot say which book or which model it is about; `Run.bare` takes one on purpose."
        )

    @classmethod
    def bare(cls, pages_dir: str, label: str = "") -> "Run":
        return cls(
            pages_dir.rstrip("/"), None, {}, label or os.path.basename(pages_dir.rstrip("/"))
        )

    @property
    def sha256(self) -> str | None:
        return (self.snapshot.get("source") or {}).get("sha256")

    @property
    def kind(self) -> str:
        if not self.run_dir:
            return ""
        k = os.path.basename(os.path.dirname(os.path.abspath(self.run_dir)))
        return k if k in book_mod.KINDS else ""

    @property
    def policy(self) -> policy_mod.Policy:
        if not self.snapshot:
            return policy_mod.UNION
        return policy_mod.Policy.from_snapshot(self.snapshot.get("policy"))

    @property
    def level(self) -> str:
        return "hybrid" if self.snapshot.get("layout") == "own" else self.kind

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
    root: str
    name: str
    truth_dir: str
    manifest: dict = field(default_factory=dict)
    scan: str = ""

    @classmethod
    def open(cls, path: str) -> "Bench":
        path = path.rstrip("/")
        if os.path.isdir(os.path.join(path, "truth")):
            root, truth = (path, os.path.join(path, "truth"))
        elif os.path.basename(path) == "truth" and os.path.isdir(path):
            root, truth = (os.path.dirname(path), path)
        else:
            raise Unmeasurable(
                f"{path} is not a bench: expected a directory holding truth/ (and manifest.json), or the truth/ directory itself"
            )
        man = read_json(os.path.join(root, "manifest.json")) or {}
        return cls(root, os.path.basename(os.path.abspath(root)), truth, man)

    @classmethod
    def bare(cls, truth_dir: str) -> "Bench":
        truth_dir = truth_dir.rstrip("/")
        return cls(os.path.dirname(truth_dir) or ".", os.path.basename(truth_dir), truth_dir, {})

    @classmethod
    def no_truth(cls, path: str) -> "Bench":
        path = path.rstrip("/")
        man = read_json(os.path.join(path, "manifest.json"))
        if not man:
            raise Unmeasurable(
                f"{path} is not a book: expected manifest.json naming the scan it is about. Without it nothing here can be checked against the run's own snapshot."
            )
        sha = (man.get("source") or {}).get("sha256")
        if not sha:
            raise Unmeasurable(
                f"{path}/manifest.json names no source.sha256, so nothing here can be checked against the run that produced it: a run of ANOTHER book would measure clean under this name."
            )
        aside = [n for n in ("truth.new", "truth.previous") if os.path.isdir(os.path.join(path, n))]
        if aside:
            raise Unmeasurable(
                f"{path} has {'/, '.join(aside)}/ but no truth/: this is a bench whose build was interrupted, not a book without truth. Measuring it truth-free would file half a record under the full one's name. Finish the build, or remove {' and '.join(aside)}/ if the truth is gone for good."
            )
        return cls(path, os.path.basename(os.path.abspath(path)), "", man, _scan_of(path, man, sha))

    @property
    def policy(self) -> policy_mod.Policy:
        return policy_mod.UNION

    @property
    def pdf(self) -> str | None:
        if not self.truth_dir:
            return self.scan or None
        if self.scan:
            return self.scan
        if not self.manifest:
            return None
        name = (self.manifest.get("source") or {}).get("name") or f"{self.name}.pdf"
        p = os.path.join(self.root, name)
        return p if os.path.isfile(p) else None

    @property
    def sha256(self) -> str | None:
        return (self.manifest.get("source") or {}).get("sha256")

    def pages(self) -> dict:
        return page.load_pages(self.truth_dir, f"truth of {self.name}")

    def traits(self, pages: dict | None = None) -> dict:
        pages = pages if pages is not None else self.pages()
        out = {k: {s: 0 for s in TRAIT_STATES} for k in TRAITS}
        for p in pages.values():
            for k in TRAITS:
                out[k][trait_state(p.get("meta") or {}, k)] += 1
        return out

    def has_content(self, pages: dict | None = None) -> bool:
        pages = pages if pages is not None else self.pages()
        return any((b.get("content") for p in pages.values() for b in p["blocks"]))

    def book(self) -> book_mod.Book:
        return book_mod.Book(self.root, self.manifest)

    def run(self, label: str = "", kind: str = "detect") -> Run:
        d = self.book().one_run(kind, label)
        return Run.open(d, f"{kind} run {label or os.path.basename(d)} of {self.name}")

    def runs(self, kind: str = "detect") -> list:
        return self.book().runs(kind)


def same_book(bench: Bench, run: Run) -> str:
    if run.run_dir is None or bench is None or (not bench.manifest):
        return "sha256 not checked: no manifest.json or run.json beside"
    a, b = (bench.sha256, run.sha256)
    if not (a and b):
        return "sha256 not checked: the field is absent from the snapshot"
    if a != b:
        raise Unmeasurable(
            f"truth and model output are about DIFFERENT books: sha256 {a[:12]} against {b[:12]}. A number here would look sensible and mean nothing."
        )
    return f"sha256 checked: {a[:12]}"
