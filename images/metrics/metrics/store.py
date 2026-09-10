"""The book directory: where its parts live, asked by everyone"""

from __future__ import annotations
import builtins
import os
import re
import json
from metrics.log import log
from metrics import settings as config
from metrics import classes as policy_mod
from metrics.errors import Refusal

ASSETS = "assets"
SOURCE = os.path.join(ASSETS, "source")
JOURNAL = os.path.join(ASSETS, "swaps.json")


def journal_path(out_dir: str) -> str:
    return os.path.join(out_dir, JOURNAL)


LABEL_OK = re.compile("^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
BOOK_ROOTS = ("bench", "processed")


def store_of(book_dir: str) -> str:
    parent = os.path.dirname(os.path.abspath(book_dir.rstrip("/")))
    return os.path.dirname(parent) if os.path.basename(parent) in BOOK_ROOTS else config.home()


ALLOWED = (
    "manifest.json",
    "<source>.pdf",
    "truth/",
    "detect/<model>/",
    "read/<model>/",
    "look/<model>.pdf",
    "look/truth.pdf",
    "assets/",
    "book.html",
)
BESIDE_A_RUN = (".crop", ".read")
INSIDE_A_RUN = {
    "detect": ("pages", "run.json"),
    "read": (
        "pages",
        "answers",
        "crops",
        "html",
        "run.json",
        "read_with.json",
        "job.log",
        "job",
        "vllm.json",
        "vllm.log",
    ),
}
ROOT_FILES = ()


def safe_label(name: str, what: str) -> str:
    name = (name or "").strip()
    if not LABEL_OK.match(name):
        raise Refusal(
            f"{what}: {name!r} cannot be a run directory name. A label is the MODEL's name, letters, digits and . _ + - only. This one comes from the model itself (the weights' own name, the variant, the weights file), so a name like this means the weights do not declare one -- pass --run <name> and the run is filed under that."
        )
    return name


KINDS = ("detect", "read")


class Book:
    def __init__(self, root: str, manifest: dict):
        self.root = os.path.abspath(root.rstrip("/"))
        self.name = os.path.basename(self.root)
        self.manifest = manifest

    @classmethod
    def open(cls, path: str, what: str = "book") -> Book:
        path = path.rstrip("/")
        man = os.path.join(path, "manifest.json")
        if not os.path.isfile(man):
            raise Refusal(
                f"{what}: {path} is not a book directory -- no manifest.json. A book directory is made by the first command that writes into it, and the manifest is what says WHICH PDF it is about; without it a page set can be measured against a book nobody named."
            )
        import json

        with open(man, encoding="utf-8") as f:
            return cls(path, json.load(f))

    @classmethod
    def list(cls, root: str) -> builtins.list[str]:
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

    @property
    def pdf(self) -> str | None:
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

    def run_dir(self, kind: str, label: str) -> str:
        if kind not in KINDS:
            raise Refusal(f"{kind!r} is not a kind of run; I know {KINDS}")
        return os.path.join(self.root, kind, safe_label(label, kind))

    def runs(self, kind: str) -> builtins.list[str]:
        if kind not in KINDS:
            raise Refusal(f"{kind!r} is not a kind of run; I know {KINDS}")
        base = os.path.join(self.root, kind)
        if not os.path.isdir(base):
            return []
        return sorted(
            (
                n
                for n in os.listdir(base)
                if os.path.isfile(os.path.join(base, n, "run.json"))
                and os.path.isdir(os.path.join(base, n, "pages"))
            )
        )

    def one_run(self, kind: str, label: str = "") -> str:
        if label:
            d = self.run_dir(kind, label)
            if not os.path.isdir(d):
                raise Refusal(
                    f"{self.name}: no {kind} run labelled {label!r}. There is {self._listing(kind)}"
                )
            return d
        got = self.runs(kind)
        if len(got) == 1:
            return self.run_dir(kind, got[0])
        if not got:
            raise Refusal(
                f"{self.name} has no {kind} run at all. Make one first: "
                + (
                    f"`books detect {self.root}`"
                    if kind == "detect"
                    else "`books read <detect dir>` -- level two does not write into the book directory yet, see the header"
                )
            )
        raise Refusal(
            f"""{self.name} has {len(got)} {kind} runs and none was named: {", ".join(got)}. Say --run <label>; measuring "the" run when there are several would file the number against whichever sorted first."""
        )

    def _listing(self, kind: str) -> str:
        got = self.runs(kind)
        return ", ".join(got) if got else f"no {kind} run in this book"


def guard_identity(
    run_dir: str, identity: str, pages_spec: str = "", what: str = "this run"
) -> None:
    import json

    snap = os.path.join(run_dir, "run.json")
    if not os.path.isfile(snap):
        return
    try:
        with open(snap, encoding="utf-8") as f:
            was = json.load(f)
    except (OSError, ValueError) as e:
        raise Refusal(
            f"{snap} cannot be read ({type(e).__name__}), and it is what says whether {what} is the same experiment as the one already there. Remove the directory or give --run a new label."
        )
    old = was.get("identity")
    if old is None:
        raise Refusal(
            f"{run_dir} holds a run whose snapshot records no identity -- it predates them -- so there is no telling whether {what} is the same experiment. Give --run a new label, or remove it."
        )
    if old != identity:
        raise Refusal(
            f"{run_dir} holds a DIFFERENT experiment: identity {old[:12]} against {identity[:12]}. Same model, other conditions -- a knob the run reads, or other weights. Writing here would leave one snapshot over two runs' pages. Give --run a new label and the two stand side by side, which is what labels are for."
        )
    if pages_spec:
        raise Refusal(
            f"{run_dir} already holds a run, and --pages {pages_spec} would write a PART of one over it. The identity cannot see a page selector -- it is over the model and the knobs -- so the snapshot would describe a run that never happened over pages left from the one that did. Give --run a new label, or remove the directory: its two sibling refusals say both and this one said only the first, which made re-running a three-page smoke test look forbidden."
        )


def page_files(d: str) -> tuple[int, str]:
    if not os.path.isdir(d):
        return (0, "not a directory")
    names = sorted((f for f in os.listdir(d) if f.endswith(".json") and f != "run.json"))
    if not names:
        return (0, "no json files at all")
    try:
        with open(os.path.join(d, names[0]), encoding="utf-8") as f:
            first = json.load(f)
    except (OSError, ValueError) as e:
        return (0, f"{names[0]} does not read as json ({type(e).__name__})")
    if not (isinstance(first, dict) and "blocks" in first and ("index" in first)):
        return (
            0,
            f"json files {len(names)}, but {names[0]} is not a layout page: no blocks/index fields",
        )
    return (len(names), "")


def pages_dir(path: str, what: str) -> str:
    if not os.path.exists(path):
        raise Refusal(
            f"{what}: no path {path}. Expected a `books detect` run directory (pages/ and run.json in it) or the directory of layout pages itself (*.json)."
        )
    sub = os.path.join(path, "pages")
    (here, why_here), (there, why_sub) = (page_files(path), page_files(sub))
    if there and (not here):
        log(f"{what}: given a run directory, taking the pages from {sub} — there are {there}")
        return sub
    if here:
        return path
    raise Refusal(
        f"{what}: no layout pages found. In {path} — {why_here}; in {sub} — {why_sub}. Expected a `books detect` run directory (pages/ and run.json in it) or the page directory itself. There is nothing to count — and that is not a zero of losses."
    )


def run_dir(path: str, what: str) -> str:
    if not os.path.exists(path):
        raise Refusal(
            f"{what}: no path {path}. Expected a `books detect` run directory — the one holding run.json."
        )
    if os.path.exists(os.path.join(path, "run.json")):
        return path
    up = os.path.dirname(os.path.abspath(path.rstrip("/")))
    if page_files(path)[0] and os.path.exists(os.path.join(up, "run.json")):
        log(f"{what}: given a page directory, taking the snapshot from {up}")
        return up
    raise Refusal(
        f"{what}: no run.json in {path}. Expected a `books detect` run directory (pages/ and run.json in it), not a page directory and not a book root."
    )


def snapshot_beside(pages_dir: str) -> dict | None:
    d = os.path.abspath(pages_dir.rstrip("/"))
    for at in (d, os.path.dirname(d)):
        p = os.path.join(at, "run.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                snap = json.load(f)
            return snap if isinstance(snap, dict) else {}
    return None


def policy_beside(pages_dir: str) -> policy_mod.Policy:
    snap = snapshot_beside(pages_dir)
    if snap is None:
        return policy_mod.UNION
    return policy_mod.Policy.from_snapshot(snap.get("policy"))


def pdf_of(detect_dir: str) -> str:
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)["source"]["path"]


def home_for(run_dir: str, store: str) -> str:
    up = os.path.dirname(os.path.dirname(os.path.abspath(run_dir.rstrip("/"))))
    if os.path.isfile(os.path.join(up, "manifest.json")):
        return up
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    stem = os.path.splitext(os.path.basename(snap["source"]["path"]))[0]
    safe = re.sub("[^\\w.,()-]+", "-", stem, flags=re.UNICODE).strip("-")[:80]
    return os.path.join(store, "processed", safe or "book")
