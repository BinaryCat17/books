"""Swapping a block inside a finished book: level two in place, and undo.

`swap.py` keeps the promise over strings; files, journal and time live here. A
swap without undo is an edit of the book, so the journal keeps a stack per
anchor rather than the last value: two swaps in a row unwind one step at a time,
and after a full unwind the book matches the original byte for byte.

Not one call to a model here. This layer puts ready markup where an image was;
producing it is `books read`'s business.
"""
import hashlib
import json
import os
import time

from booksmith.processing.assemble import swap
from booksmith.core import book
from booksmith.core.book import ASSETS, SOURCE
from booksmith.core import page
from booksmith.processing.assemble.html import (
    observed,
    torn_grid,
    torn_of)
from booksmith.core.errors import Refusal
from booksmith.core.log import log



class SwapError(Refusal):
    """Something is wrong with the swap — and it is said out loud."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _same(now: str, promised: str) -> bool:
    """Does what lies in the block match what the swap put there?

    A function rather than a line inside `undo` so a probe can
    break it: a check that cannot be broken is not proved.
    """
    return _sha256(now) == promised


def book_path(out_dir: str) -> str:
    p = os.path.join(out_dir, "book.html")
    if not os.path.exists(p):
        raise SwapError(f"no {p}: run books html first")
    return p


def load_journal(out_dir: str) -> dict:
    """Read the journal. An unreadable journal is trouble out loud, not an empty
    one.

    "No journal" and "journal unreadable" are different zeros, and the second
    must stop the work: `put` writes over a stub at once, and the undo stack of
    every earlier swap is then gone for good.
    """
    # `book.journal_path` is the one rule, so reading and writing cannot part.
    p = book.journal_path(out_dir)
    if not os.path.exists(p):
        return {"book": "book.html", "swaps": {}}
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
    except ValueError as e:
        raise SwapError(
            f"{p} does not read as json ({e}), and it holds the undo stack "
            f"of the WHOLE book. It may not be taken for an empty journal: "
            f"the very next swap would write its one record over the stump "
            f"and there would be nothing left to undo with. Sort the file out "
            f"by hand -- a {p}.tmp from a broken write may lie "
            f"alongside.") from None
    if not isinstance(j, dict):
        raise SwapError(
            f"{p}: {type(j).__name__} at the top level, and a journal is an "
            f"object. The file is not from this command, or it is broken.")
    j.setdefault("swaps", {})
    return j


def save_journal(out_dir: str, j: dict) -> str:
    """Write the journal atomically: a failed plain write would leave a stub
    where the undo stack of the whole book was."""
    # Write where we read, by the same rule `load_journal` asks.
    p = book.journal_path(out_dir)
    # The kitchen may not exist yet: a swap can work over a book it did not
    # build, and refusing here would report a failed swap over a missing folder.
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    page.write_json(p, j, indent=1)
    return p


def _check_fragment(fragment: str, anchor: str) -> None:
    """The fragment we place must carry no foreign block marks.

    A mark inside it is a ghost anchor: the next swap's `span` sees two opening
    marks and refuses, far from where the trouble was made.
    """
    bad = swap._marks_in(fragment)
    if bad:
        raise SwapError(
            f"the inserted fragment carries block marks {bad}: they become "
            f"ghost anchors, and the next swap will refuse to work. The "
            f"second level returns THE MARKUP OF A BLOCK, not pieces of the "
            f"book.")
    if not fragment.strip():
        raise SwapError(
            f"the inserted fragment is empty. An empty swap erases block "
            f"{anchor} from the book, and by sight that is indistinguishable "
            f"from \"the model kept quiet\". If the block really must go, say "
            f"so explicitly by another route.")


def _unclosed_comment(text: str) -> int:
    """Where an unclosed `<!--` starts, or -1. HTML comments do not nest: the
    first `-->` closes."""
    i = text.find("<!--")
    while i >= 0:
        j = text.find("-->", i + 4)
        if j < 0:
            return i
        i = text.find("<!--", j + 3)
    return -1


def _check_comments(body: str, anchor: str) -> None:
    """An unfinished comment in what will lie in the book.

    Such a fragment carries no block marks, is not empty, has its kind declared
    and changes no anchor, while the browser stretches the comment to our closing
    block mark and eats the wrapper's closing tag with it. Runs after the anchor
    comparison, so as not to take away the only case that comparison is proved
    by, and looks at the body after rendering: `render` escapes `<` for `text`,
    `latex` and `otsl`, where a bare `<!--` is a lawful swap.
    """
    i = _unclosed_comment(body)
    if i < 0:
        return
    raise SwapError(
        f"in the swap for {anchor} a comment is opened and not closed: "
        f"{body[i:i+40]!r}. The browser stretches it to the nearest `-->`, "
        f"which is OUR closing block mark: it eats that and the wrapper's "
        f"closing tag, and the rest of the book ends up inside an unclosed "
        f"element. The anchor set does not change, so nobody would see it.")


def block_roles(out_dir: str) -> dict:
    """Every role at once. Reads `blocks.json` once.

    A book holds thousands of blocks, and `block_role` reads the file for each
    of them. Same rule, same file, fewer reads.
    """
    p = os.path.join(out_dir, ASSETS, "blocks.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def block_role(out_dir: str, anchor: str) -> str:
    """A block's role from the build's `blocks.json`, or `unknown`.

    Read, not assigned: level two is sometimes wanted for a text block too, and
    the book is read by that attribute later.
    """
    p = os.path.join(out_dir, ASSETS, "blocks.json")
    if not os.path.exists(p):
        return "unknown"
    try:
        with open(p, encoding="utf-8") as f:
            return ((json.load(f).get(anchor) or {}).get("role")
                    or "unknown")
    except (ValueError, OSError):
        return "unknown"


def _anchors_unchanged(before, after) -> bool:
    """Does the book hold the same anchor set after the swap?

    A seam for a probe, like `_same`. It catches what the fragment check does
    not: an unclosed mark (`<!--bs:xyz` with no `-->`) holds no complete marks,
    and `swap.anchors` finds a `-->` further down and bears a junk anchor.
    """
    return after == before


def render(fragment: str, kind: str) -> str:
    """The model's answer -> what the browser shows. Translation, not repair.

    `page.KINDS` declares four kinds, and inserting all four as HTML spoils
    three: OTSL runs its cells into one line, `text` loses `<n/a>` to the
    browser, `latex` goes in raw. The model's bytes go nowhere — the answer lies
    in `pages/*.json` and the reading's `answers/`, the journal keeps what was
    placed whole, and this translation replays from them.
    """
    import html as _h
    from booksmith.core import otsl
    if kind == "otsl":
        out = otsl.to_html(fragment)
        if out:
            return out
        # A table was asked for and the answer holds no OTSL. No reason to show
        # emptiness: the answer stays visible, its kind named in the wrapper.
        return "<pre>" + _h.escape(fragment) + "</pre>"
    if kind in ("text", "latex"):
        # Characters, not markup: `<n/a>` must stay in sight.
        return "<pre>" + _h.escape(fragment) + "</pre>"
    return fragment                      # html — as is, byte for byte


def _wrap_fragment(anchor: str, fragment: str, kind: str, source: str,
                   role: str = "unknown", torn: bool | None = None) -> str:
    """Wrap level two's answer in our wrapper, its bytes untouched.

    The wrapper is marked, never the content: the recognised is untouchable. A
    table shape that cannot exist and an answer cut off at the ceiling become
    marks rather than refusals — a refusal hides the defect from the measurement,
    leaving the book one table short with nothing said. The truncation mark
    travels in with the fragment, the swap replacing the build's own `<div>`.
    `torn=None` is "not asked", not "whole": the mark needs an explicit True.
    """
    import html as _h
    shape = torn_grid(_grid_tally(fragment, kind))
    bad = (f' data-table-shape="{_h.escape(shape, quote=True)}"'
           if shape else "")
    if torn:
        bad += ' data-truncated="yes"'
    return (f'<div id="{anchor}" data-role="{_h.escape(role)}" '
            f'data-level="2" data-kind="{_h.escape(kind)}" '
            f'data-placed-by="{_h.escape(source)}"{bad}>' + render(fragment, kind)
            + "</div>")


def _count_in_book(tally: dict, misshapen: list, anchor: str,
                    body: str, kind: str) -> None:
    """What went into the book — as a number.

    Called after the guards and before the `continue` on "already there": among
    the newly placed it would miss what a repeat run leaves standing, and above
    the guards it would count blocks that were refused.
    """
    shape = torn_grid(_grid_tally(body, kind))
    if shape:
        tally["impossible_table_shape"] += 1
        misshapen.append(f"{anchor}: {shape}")
    if kind != "otsl":
        return
    from booksmith.core import otsl as _otsl
    cells, t = _otsl.layout(body)
    announced = t.get("merges", 0)
    # Declared and placed are counted apart, from the model's marks and from
    # cells that really got a span: equated, they hide a translation loss.
    placed = sum(1 for c in cells if c["rows"] > 1 or c["cols"] > 1)
    tally["merges_declared"] += announced
    tally["merges_in_book"] += placed
    tally["tables_with_merges"] += bool(announced)


def _grid_tally(fragment: str, kind: str) -> dict | None:
    """The fragment's grid, if it is OTSL. `None` is "not measurable by grid",
    not "whole".

    Parsing and judgement stay split: `otsl.parse` returns a tally, `torn_grid`
    judges the shape, and merging them would make a second place where
    "impossible table" is decided.
    """
    if kind != "otsl" or not fragment:
        return None
    from booksmith.core import otsl
    try:
        _, t = otsl.parse(fragment)
    except Exception:
        return None
    return t


def put_into(html: str, anchor: str, fragment: str, kind: str, source: str,
             role: str, torn: bool | None = None) -> tuple[str, dict, str]:
    """The core of a swap: all five guards, and not one touch of the disk.

    In order: an undeclared kind; a foreign mark inside the fragment or an empty
    fragment (`_check_fragment`); no such anchor in the book; the anchor set
    changed by the swap; an unfinished comment in what will lie in the book.
    Returns (new book, journal entry, what was removed). `from_read` places
    swaps by the hundred through this same function, one read of the book for
    all of them, rather than owning a second copy of the guards.
    """
    if kind not in page.KINDS:
        raise SwapError(f"kind {kind!r} is not declared: I know only {page.KINDS}")
    _check_fragment(fragment, anchor)

    before = swap.anchors(html)
    if anchor not in before:
        raise SwapError(
            f"there is no anchor {anchor} in the book. There are "
            f"{len(before)} others; names are per page, like p0042-b17 — look "
            f"in blocks.json.")
    body = _wrap_fragment(anchor, fragment, kind, source or "by hand",
                          role=role, torn=torn)

    # A repeat is not work: the same bytes again leave the book unchanged while
    # the undo stack gains a step. The finished body is compared, not the raw
    # fragment, so the same answer from another model is work and goes through.
    if swap.get(html, anchor) == body:
        return html, None, body

    new_html, taken = swap.swap(html, anchor, body)
    after = swap.anchors(new_html)
    if not _anchors_unchanged(before, after):
        lost = sorted(set(before) - set(after))
        got = sorted(set(after) - set(before))
        raise SwapError(
            f"the swap for {anchor} changed the book\'s anchor set: lost "
            f"{lost}, appeared {got}. The book is not written.")
    _check_comments(body, anchor)
    entry = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "placed_by": source or "by hand",
        "kind": kind,
        "sha256_placed": _sha256(body),
        "model_answer": fragment,
        "sha256_model_answer": _sha256(fragment),
        "removed": taken,
        "sha256_removed": _sha256(taken),
    }
    return new_html, entry, body


def put(out_dir: str, anchor: str, fragment: str, kind: str = "html",
        source: str = "") -> dict:
    """Place one piece of markup where a block is. Magnitudes, not "done".

    The rule lives wholly in `put_into`; only the I/O around it is here. The
    truncation flag is taken here too, from the observations inside the book
    (`assets/source/answers/`): with no source there `torn_of` returns `None`,
    "nothing to say", which is not "whole".
    """
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    new_html, entry, body = put_into(
        html, anchor, fragment, kind, source, block_role(out_dir, anchor),
        torn=torn_of(observed(os.path.join(out_dir, SOURCE)).get(anchor)))
    if entry is None:
        # "The block already carries exactly this" and "the swap failed" are
        # different answers; a bare "placed 0" would merge them.
        j = load_journal(out_dir)
        depth = len(j["swaps"].get(anchor, []))
        log(f"{anchor}: EXACTLY THIS ALREADY STANDS there ({kind}, "
            f"{source or 'by hand'}) — the book is untouched, undo stack "
            f"{depth}")
        return {"anchor": anchor, "placed": 0, "already_placed": True,
                "removed": 0, "anchor_count": len(swap.anchors(html)),
                "undo_depth": depth}
    taken = entry["removed"]
    j = load_journal(out_dir)
    j["swaps"].setdefault(anchor, []).append(entry)
    # Journal before book, for the same reason as in `undo`.
    save_journal(out_dir, j)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)
    after = swap.anchors(new_html)
    log(f"{anchor}: placed {len(body)} chars ({kind}, "
        f"{source or 'by hand'}), taken {len(taken)}; anchors in the book "
        f"{len(after)}, undo stack {len(j['swaps'][anchor])}")
    return {"anchor": anchor, "placed": len(body), "removed": len(taken),
            "anchor_count": len(after), "undo_depth": len(j["swaps"][anchor])}


def undo(out_dir: str, anchor: str) -> dict:
    """Return what stood before the last swap."""
    path = book_path(out_dir)
    j = load_journal(out_dir)
    stack = j["swaps"].get(anchor) or []
    if not stack:
        raise SwapError(
            f"nothing to undo: {anchor} was never swapped. This is NOT the "
            f"same as \"the undo failed\" — the journal says nothing about "
            f"this anchor.")

    with open(path, encoding="utf-8") as f:
        html = f.read()
    rec = stack[-1]

    # What lies there now against what the swap put there: "undo" sounds safe.
    now = swap.get(html, anchor)
    if not _same(now, rec["sha256_placed"]):
        raise SwapError(
            f"what lies at {anchor} is not what the last swap put there "
            f"(sha256 {_sha256(now)[:12]} against "
            f"{rec['sha256_placed'][:12]}). The book was edited past the "
            f"journal; an undo would erase that edit. Sort it out by hand.")

    new_html = swap.restore(html, anchor, rec["removed"])

    # Compare what came back, not what the journal promised, and print the
    # computed hash: otherwise the command produces someone else's proof.
    back = swap.get(new_html, anchor)
    got = _sha256(back)
    if got != rec["sha256_removed"]:
        raise SwapError(
            f"undoing {anchor} returned NOT what the swap removed: computed "
            f"{got[:12]}, the journal promised {rec['sha256_removed'][:12]} "
            f"({len(back)} chars against the promise). The journal was edited "
            f"past this command. The book is not written.")

    stack.pop()
    if not stack:
        # The entry stays: an empty stack and "this anchor was never touched"
        # are different states, and `pop` would merge them.
        j["swaps"][anchor] = []
    # The journal is written before the book: a failure on it would otherwise
    # leave a changed book with no undo record.
    save_journal(out_dir, j)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)

    log(f"{anchor}: undone, computed sha256 {got[:12]} "
        f"({len(back)} chars, swap of {rec['when']}); "
        f"left in the stack {len(stack)}")
    return {"anchor": anchor, "restored": len(back),
            "undo_depth": len(stack)}


def status(out_dir: str) -> dict:
    """What is swapped and what is still an image — journal compared against book.

    The journal alone drifts from the book silently: `books html --out` into the
    same directory rebuilds knowing nothing of `swaps.json`, and the journal then
    claims a swap over a block holding the original image.
    """
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    j = load_journal(out_dir)
    a = swap.anchors(html)

    live, empty, drifted, gone = {}, 0, [], []
    for k, v in j["swaps"].items():
        if not v:
            empty += 1                    # swapped, then fully undone
            continue
        if k not in a:
            gone.append(k)                # no such anchor in the book at all
            continue
        live[k] = len(v)
        if _sha256(swap.get(html, k)) != v[-1]["sha256_placed"]:
            drifted.append(k)

    log(f"anchors in the book {len(a)}; blocks swapped {len(live)}, "
        f"swaps in all {sum(live.values())}, undone to the end {empty}")
    # Three different zeros, each on its own line. Merging them shows the
    # operator "all fine" on a book that has drifted from its journal.
    if not a:
        log("no anchors at all — this is not \"everything swapped\", it is "
            "an empty book")
    elif not j["swaps"]:
        log("no swaps: the second level has not walked this book yet")
    elif not live:
        log(f"no live swaps: all {empty} undone to the end — this is NOT "
            f"the same as \"never walked\"")
    if drifted:
        log(f"DRIFTED FROM THE BOOK: {len(drifted)} blocks "
            f"({', '.join(drifted[:5])}"
            f"{'…' if len(drifted) > 5 else ''}) — what lies there is not "
            f"what the last swap put. The book was rebuilt or edited past the "
            f"journal; an undo on these will refuse to work")
    if gone:
        log(f"anchors from the journal missing from the book: {len(gone)} "
            f"({', '.join(gone[:5])}) — the book is built from another "
            f"detection")
    return {"anchor_count": len(a), "blocks_swapped": len(live),
            "swaps_total": sum(live.values()), "fully_undone": empty,
            "drifted": len(drifted), "missing_from_book": len(gone),
            "per_anchor": live}


def source_of(out_dir: str) -> str | None:
    """Which reading directory the book was built from — by its own snapshot.

    `books html` writes `args.detect` into `assets/run.json`, so the book
    remembers what made it. `None` if there is no snapshot, the field is empty or
    the directory is gone: the caller needs `--from` either way.
    """
    # The source inside the book first: `assets/source` is the only path that
    # survives the directory moving, the snapshot recording an absolute one.
    own = os.path.join(out_dir, SOURCE)
    if os.path.isdir(os.path.join(own, "pages")):
        return own

    p = os.path.join(out_dir, ASSETS, "run.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            snapshot = json.load(f)
    except ValueError:
        return None
    path = ((snapshot.get("args") or {}).get("detect") or "").strip()
    if not path or not os.path.isdir(os.path.join(path, "pages")):
        return None
    return path


def from_read(out_dir: str, read_dir: str, only_role: str = "artifact") -> dict:
    """Place in the book everything level two read. One at a time, undoable.

    The build draws an artifact as an image whatever its content, a swap being
    reversible and journalled where a rebuild knows nothing of the journal; this
    is the bridge read tables and formulas reach the book by. Text blocks stay
    out by default (`only_role="artifact"`): the build prints them as `<p>` on
    non-empty content, and swapping them too would give one block two owners.
    """
    import glob as _glob

    pages = sorted(_glob.glob(os.path.join(read_dir, "pages", "*.json")))
    if not pages:
        raise SwapError(f"no pages/*.json in {read_dir} — this is not a "
                        f"`books read` directory")
    tally = {"block_count": 0, "placed": 0, "already_placed": 0,
             "nothing_to_place": 0, "wrong_bucket": 0, "refused": 0,
             "chars": 0, "impossible_table_shape": 0,
             # the same model bytes under a new wrapper of ours: a real swap
             # and a stack step, but calling it "placed" would journal work
             # that never happened
             "rewrapped": 0,
             # spans are mute without a number, and a regression of them back
             # to zero would be invisible
             "merges_declared": 0, "merges_in_book": 0,
             "tables_with_merges": 0}
    refused = []
    # Placed and marked, listed apart: see the summary lines at the end.
    misshapen = []
    # Reading observations, from where the content comes: without them the
    # truncation mark is lost on the blocks that reach the reader as markup.
    obs = observed(read_dir)
    src = os.path.basename(os.path.abspath(read_dir))

    # Read and write once, not per swap: calling `put` here would bring a reread
    # of the whole book with it. The guards are the same ones, not repeated.
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    roles = block_roles(out_dir)
    j = load_journal(out_dir)

    for fp in pages:
        with open(fp, encoding="utf-8") as f:
            pg = json.load(f)
        for b in pg.get("blocks", []):
            tally["block_count"] += 1
            anchor = page.anchor(pg["index"], b["block_id"])
            role = (roles.get(anchor) or {}).get("role") or "unknown"
            if only_role and role != only_role:
                tally["wrong_bucket"] += 1
                continue
            body = b.get("content")
            if not body or not body.strip():
                tally["nothing_to_place"] += 1
                continue
            try:
                html, entry, _ = put_into(
                    html, anchor, body, b.get("kind") or "html", src, role,
                    # One rule, and it is called: an inline copy collapsed
                    # "not asked" into "finished" and, unsubstitutable, kept
                    # the probes off the book path.
                    torn=torn_of(obs.get(anchor)))
            except SwapError as e:
                tally["refused"] += 1
                refused.append(f"{anchor}: {str(e)[:80]}")
                continue
            # Counted past the refusals — only then does the number describe
            # the book and not this run's work. See `_count_in_book`.
            _count_in_book(tally, misshapen, anchor, body,
                            b.get("kind") or "html")
            if entry is None:            # exactly this already lies there
                tally["already_placed"] += 1
                continue
            # Compared by the sha of the model's answer, not the finished body:
            # the body differs by our wrapper, and what was paid for is the
            # answer.
            previous = j["swaps"].get(anchor) or []
            if previous and previous[-1].get("sha256_model_answer") == \
                    entry.get("sha256_model_answer"):
                tally["rewrapped"] += 1
            j["swaps"].setdefault(anchor, []).append(entry)
            tally["placed"] += 1
            tally["chars"] += len(body)

    # Journal before book, as in `undo`: a break between them leaves undo
    # knowing of a swap the book does not have, which is the safer half.
    if tally["placed"]:
        save_journal(out_dir, j)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    log(f"blocks in the reading {tally['block_count']}: placed "
        f"{tally['placed']} ({tally['chars']} chars), already there "
        f"{tally['already_placed']}, nothing to place "
        f"{tally['nothing_to_place']}, wrong bucket {tally['wrong_bucket']}, "
        f"refused {tally['refused']}"
        + (f"; of those placed {tally['rewrapped']} — REWRAPPED: the model's "
           f"bytes are the same, OUR wrapper changed, no new work here"
           if tally["rewrapped"] else ""))
    # Four different zeros, each with its own cause: "everything is already
    # there" is not "not one block landed", and neither is a verdict on the
    # reading.
    if not tally["placed"]:
        if not tally["block_count"]:
            log("no blocks in the reading at all — this is not "
                "\"everything is already there\"")
        elif tally["already_placed"]:
            log(f"the book is ALREADY ASSEMBLED from this reading: "
                f"{tally['already_placed']} blocks carry exactly what is in "
                f"it. Nothing touched, no undo stack grew — a repeat is free "
                f"here")
        elif tally["nothing_to_place"] == tally["block_count"]:
            log("the model read NOT ONE block — there is nothing to place, "
                "and this is NOT \"the book is already assembled\"")
        else:
            log(f"not one block landed: no \"{only_role}\" bucket among "
                f"what was read")
    for r in refused[:5]:
        log(f"  REFUSED {r}")
    # Placed does not mean good, and this prints always, zero included: a line
    # that vanishes at zero reads as "this never happens". The two merge numbers
    # stand apart — apart means the translation lost a merge the model declared.
    # Both lines say "in the book", not "placed", because they describe the whole
    # book and not this run's work.
    log(f"  merges: the model declared {tally['merges_declared']} in "
        f"{tally['tables_with_merges']} tables, in the book stand "
        f"{tally['merges_in_book']}"
        + ("" if tally["merges_declared"] == tally["merges_in_book"]
           else f" — DIVERGED by "
                f"{tally['merges_declared'] - tally['merges_in_book']}"
                f"; these are non-rectangular merges of a truncated answer, "
                f"printed flat and not straightened"))
    log(f"  impossible table shape at {tally['impossible_table_shape']} "
        f"blocks OF THE BOOK — the model's answer is left byte for byte, "
        f"marked data-table-shape"
        + (f": {'; '.join(misshapen[:3])}" if misshapen else ""))
    # A mark no CSS draws is a mark in the journal only. The CSS is not edited
    # here: the book is the build's product, and a swap has no business in it.
    if tally["placed"] or tally["impossible_table_shape"]:
        # Look at what is already read: a check for a warning must not cost the
        # reread this function exists to avoid.
        _book = html
        absent = [name for name, rule in
               (("truncation marks", "[data-truncated]"),
                ("table borders", "border-collapse"),
                ("wide-table scrolling", 'div[data-level="2"]'))
               if rule not in _book]
        if absent:
            log(f"  WARNING: the book is built with the older CSS — it has "
                f"no rules for {', '.join(absent)}. The marks and merges ARE "
                f"in the markup, but the eye cannot see them. Rebuild: `books "
                f"html {os.path.join(out_dir, SOURCE)} --out {out_dir}` and "
                f"repeat `books apply --from` (a repeat is free)")
    tally["refusals"] = refused
    tally["impossible_tables"] = misshapen
    return tally
