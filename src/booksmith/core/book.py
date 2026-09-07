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
`processed/<name>/`, so `runs("read")` is always empty and `build` has no
caller outside this file. They were advertised here and in CLAUDE.md as
though they existed, which made 3b read as finished when a third of it is
not. Step 3c moves the two commands onto this layout.

THE LABEL IS THE MODEL'S NAME (`Detector.label`), so two models measured on
one book do not overwrite each other -- which is what "run every detector and
put the numbers side by side" needs, and what a single `detect/` could not
give. `run.json` carries `identity`, and a command about to write a DIFFERENT
identity under an existing label refuses and asks for `--run`.
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
    def open(cls, path: str, what: str = "book") -> "Book":
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
                   f"`books read <detect dir>` -- level two does not write "
                   f"into the book directory yet, see the header"))
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
