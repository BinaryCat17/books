"""Swapping a block inside a finished book: the second level in place, and undo.

The whole two-level scheme was built for this — "a swap can be checked, undone
and redone by another model without touching the book". `swap.py` keeps that
promise over strings; files, journal and time live here.

WHY THE JOURNAL IS MANDATORY. A swap without undo is an edit of the book: the
second level will be wrong and there will be nothing to return. The journal
keeps a STACK per anchor, not the last value — two swaps in a row (the VLM
answered, the answer was poor, redone by another model) unwind one step at a
time, in reverse, where a flat "what was here" field would lose the middle
state silently. After a full unwind the book matches the original byte for byte.

DELIBERATELY ABSENT: not one call to a model. This layer only puts ready markup
where an image was; producing it is `books read`'s business, and it has run —
412 swaps on "Refractory technology".
"""
import hashlib
import json
import os
import time

from . import swap
# The block anchor is built by ONE rule for the whole project. A third copy
# lived here (in `from_read`), and drift from `html.anchor_of` would be silent:
# `put` answers "no such anchor" for every block and the command prints a
# healthy "refused N" instead of "the naming scheme has split".
from .html import (ASSETS, SOURCE, anchor_of, journal_path, observed, torn_grid,
                   torn_of)

# The swap journal is KITCHEN, not book: it lives in `assets/`, and the build
# root keeps exactly one self-contained file, `book.html`.
JOURNAL = os.path.join(ASSETS, "swaps.json")
# Content kinds the second level may return. DECLARED, not "any string": `kind`
# travels into the journal and into the book as an attribute, and a typo would
# silently become a kind nobody agreed on. Names as in the block contract
# (`models/base.py`), minus its `none` — an unread block has nothing to place.
KINDS = ("html", "otsl", "latex", "text")


class SwapError(RuntimeError):
    """Something is wrong with the swap — and it is said out loud."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _same(now: str, promised: str) -> bool:
    """Does what lies in the block match what the swap put there?

    A function and not a line inside `undo` purely for the mutation battery: a
    check that cannot be broken is not proved. Same project rule as for the
    metrics — first make sure the number can fall.
    """
    return _sha256(now) == promised


def book_path(out_dir: str) -> str:
    p = os.path.join(out_dir, "book.html")
    if not os.path.exists(p):
        raise SwapError(f"no {p}: run books html first")
    return p


def load_journal(out_dir: str) -> dict:
    """Read the journal. An UNREADABLE journal is trouble out loud, not an empty
    one.

    "No journal" and "journal unreadable" are different zeros, and the second
    must stop the work: returning an empty one would cost the whole book, since
    `put` writes over the stub at once and the undo stack of every earlier swap
    is gone for good.
    """
    # OLD LAYOUT — NOT AN EMPTY JOURNAL. The journal moved into `assets/`, and
    # books built before the move keep it in the root. Missing that, we
    # declared "no swaps: the second level has not walked this book yet" where
    # the undo stack of all the paid work lay: 412 swaps on `ruall.read/html`,
    # 17 on `ru20.read/html`. Worse, the next swap would start a SECOND journal
    # and leave the first unreachable. The rule is `html.journal_path`, asked
    # by the rebuild guard too -- it used to have a third copy that looked only
    # under `assets/`.
    p = journal_path(out_dir)
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
    """Write the journal ATOMICALLY: temp file alongside, then `os.replace`.

    `open(p, "w")` truncates the old file FIRST, so anything that happens next
    (no space, Ctrl-C inside `json.dump`, a disk pulled) leaves a stub where the
    undo stack of the WHOLE book was — one broken write takes away the ability
    to undo ANY earlier swap. Measured: a journal of 3 swaps of one anchor, 2101
    bytes, `json.dump` killed midway. The old way left a 1076-byte stub
    unreadable as json; the new way leaves the old journal intact (2101 bytes,
    3 swaps) and the stub in `swaps.json.tmp`, where it changes nothing.

    `os.replace` is atomic within one filesystem, so the temp file goes BESIDE
    the journal, not into /tmp.
    """
    # WRITE WHERE WE READ, by the same rule `load_journal` asks.
    p = journal_path(out_dir)
    # The kitchen may not exist yet: `books html` creates it, and a swap can
    # work over a book it did not build. Refusing here would report "the swap
    # failed" where only a folder failed.
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
        f.flush()
        # Bytes to disk BEFORE the rename: without fsync the rename can land
        # ahead of the content, and a power cut leaves a zero-length file under
        # the right name.
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return p


def _check_fragment(fragment: str, anchor: str) -> None:
    """The fragment we place must carry no foreign block marks.

    A mark inside it is a ghost anchor: `swap.anchors` counts one extra, the
    next swap's `span` sees two opening marks and refuses, and the trouble
    surfaces far from where it was made. One pass over the string catches it in
    place.
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

    THE FIFTH GUARD, and it exists because the four before it missed this one
    every time. A fragment `<table>…</table><!-- did not finish` carries no
    block marks (`_check_fragment` is silent), is not empty, has its kind
    declared, and does NOT CHANGE the anchor set — `swap.anchors` looks for
    `<!--bs:`, and a bare `<!--` is no anchor to it. Measured on `bench/atlas`
    (26 blocks): the command answered "placed 154, taken 175, anchors 26"
    while the browser read `<!-- did not finish</div><!--/bs:p0001-b0-->` as
    ONE comment, eating OUR closing `</div>` and OUR closing mark. Visibly: div
    opened 0 -> 1, closed 0 -> 0, figure 26 -> 25, and the rest of the book
    moved inside the unclosed div.

    The mirror half — an unclosed OPENING mark (`<!--bs:… ` with no `-->`) — is
    left to the anchor comparison, and this guard runs AFTER it on purpose: it
    would otherwise take away the only case by which that comparison is proved.

    We look at the BODY AFTER rendering: `render` escapes `<` for `text`,
    `latex` and `otsl`, and complaining about `<!--` there would refuse a lawful
    swap.
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
    """Every role at once. Reads `blocks.json` ONCE.

    `block_role` was called once per block, and a book holds six thousand:
    rebuilding "Refractory technology" spent gigabytes of reading on it. Same
    rule, same file, fewer reads.
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

    Read, not assigned: the wrapper used to set the artifact role ALWAYS, while
    `blocks.json` under the same anchor could say text. The second level is
    sometimes needed by a text block too, and the book is read by that attribute
    later.
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

    A seam for the battery, like `_same`. It catches what the fragment check
    does NOT: an unclosed mark (`<!--bs:xyz` with no `-->`) holds no complete
    marks, `_check_fragment` lets it through, and `swap.anchors` finds a closing
    `-->` further down the book and gives birth to a junk anchor. Measured:
    `<p>text <!--bs:p0001-b9 inside</p>` yields "appeared ['p0001-b9
    inside…']", and the book is not written.
    """
    return after == before


def render(fragment: str, kind: str) -> str:
    """The model's answer -> what the browser shows. TRANSLATION, not repair.

    WHY. `KINDS` declares four kinds while the fragment was always inserted as
    HTML, and three of the four silently spoiled the book, the command reporting
    a healthy number throughout. Measured: `<fcel>Year<fcel>Total<nl>…` under
    `--kind otsl` gave the run-on "YearTotal199812,4" — no rows, no columns,
    exactly what HTML rather than Markdown was chosen for; `--kind text` lost
    "<n/a>" whole (the browser eats an unknown tag); `--kind latex` went in
    raw.

    THE MODEL'S BYTES GO NOWHERE. Display only: the answer lies in
    `pages/*.json` and the reading directory's `answers/`, the journal keeps
    what was placed, whole, and the translation replays from them. We do not
    edit the answer, we SHOW it.
    """
    import html as _h
    from .. import otsl
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
    """Wrap the second level's answer in OUR wrapper, its bytes untouched.

    We mark the wrapper, not the content: the recognised is untouchable. Marks
    written straight into the markup cost nine misses of thirty-three.

    TABLE SHAPE IS A MARK, NOT A SIXTH GUARD, and gets no ordinal on purpose —
    it rejects nobody. All five guards of `put_into` let OTSL cut off by the
    ceiling through: no foreign marks, not empty, kind declared, anchor set
    unchanged, no unfinished comment. Two tables of 104 entered "Refractory
    technology" that way, the worst `p0055-b11`: 4x4 on the scan, in the book a
    `<table>` with 2047 `<td>` in ONE row — 36 % of every cell in the book.

    WHY A MARK AND NOT A REFUSAL: a refusal hides the defect from measurement.
    The book would be silently one table short and "placed 412" become "411"
    with no explanation; a mark keeps the answer byte for byte and says so out
    loud, in the book and in the `books apply` summary.

    CEILING TRUNCATION TRAVELS INTO THE WRAPPER WITH THE FRAGMENT. The build
    marks truncated blocks `data-truncated`, but a swap puts its OWN `<div>`
    there, and the mark vanished on exactly the blocks that reached the reader
    as markup: 10 of 14 left, the four lost being those `books apply` had placed
    (two tables, a formula, a chart).

    `torn=None` is "not asked", NOT "whole": a single swap has no observations
    alongside and must not lie with a "whole" mark, so the mark goes on only on
    an explicit True.
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
    """What went into the BOOK — as a number. A separate function for the battery.

    WHERE IT BELONGS. The count moved twice and lied twice: among the newly
    placed, a repeat run over a built book printed "impossible shape at 0"
    with two impossible tables inside it; at the top of the loop it counted
    blocks the guards REFUSED to place, saying of the book what is not in it.
    One right place — after the guards, before the `continue` on "already
    there".

    Without a seam this cannot be broken: both earlier versions passed the whole
    battery green.
    """
    shape = torn_grid(_grid_tally(body, kind))
    if shape:
        tally["impossible_table_shape"] += 1
        misshapen.append(f"{anchor}: {shape}")
    if kind != "otsl":
        return
    from .. import otsl as _otsl
    cells, t = _otsl.layout(body)
    announced = t.get("merges", 0)
    # DECLARED and PLACED are counted APART, from different sources: the
    # model's marks, and cells that actually got a span. Equating them takes
    # from the instrument its only way to show a translation loss.
    placed = sum(1 for c in cells if c["rows"] > 1 or c["cols"] > 1)
    tally["merges_declared"] += announced
    tally["merges_in_book"] += placed
    tally["tables_with_merges"] += bool(announced)


def _grid_tally(fragment: str, kind: str) -> dict | None:
    """The fragment's grid, if it is OTSL. `None` is "not measurable by grid",
    not "whole".

    Their parsing and our judgement are split on purpose: `otsl.parse` returns a
    tally, `torn_grid` judges the shape. Merging them would create a second
    place where "impossible table" is decided.
    """
    if kind != "otsl" or not fragment:
        return None
    from .. import otsl
    try:
        _, t = otsl.parse(fragment)
    except Exception:
        return None
    return t


def put_into(html: str, anchor: str, fragment: str, kind: str, source: str,
             role: str, torn: bool | None = None) -> tuple[str, dict, str]:
    """THE CORE of a swap: all FIVE guards, and NOT ONE touch of the disk.

    In order: an undeclared kind; a foreign mark inside the fragment or an empty
    fragment (`_check_fragment`); no such anchor in the book; the anchor set
    changed by the swap; an UNFINISHED COMMENT in what will lie in the book. The
    count is not decoration — it is how one checks that all of them are listed,
    and "four" stood here for a while, inviting nobody to look for the fifth
    that names itself fifth two hundred lines above.

    Split out for a second consumer. `put` reads the book, places one swap and
    writes back — right when there is one swap. `from_read` places them by the
    hundred, and each used to reread the whole book and parse ALL its anchors
    twice: on "Refractory technology" (2.3 MB, 412 swaps of 6156 blocks) six
    minutes instead of seconds. A second copy of the guards would be worse than
    a slow build — two copies drifting apart is trouble already paid for.

    Returns (new book, journal entry, what was removed).
    """
    if kind not in KINDS:
        raise SwapError(f"kind {kind!r} is not declared: I know only {KINDS}")
    _check_fragment(fragment, anchor)

    before = swap.anchors(html)
    if anchor not in before:
        raise SwapError(
            f"there is no anchor {anchor} in the book. There are "
            f"{len(before)} others; names are per page, like p0042-b17 — look "
            f"in blocks.json.")
    body = _wrap_fragment(anchor, fragment, kind, source or "by hand",
                          role=role, torn=torn)

    # A REPEAT IS NOT WORK. If exactly these bytes already lie in the block the
    # book would not change, the undo stack would gain a step, and `--undo`
    # would take two calls to get the image back. Measured before this check: a
    # second `--from` on the same book reported "placed 412" with content
    # unchanged and the journal grew from 412 swaps to 824 — the depth of EVERY
    # stack became two.
    #
    # We compare the FINISHED BODY, not the raw fragment: the body carries kind,
    # source and role, so only a fully identical swap is a repeat. The same
    # fragment from another model is work, and it goes through.
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
        source: str = "", log=print) -> dict:
    """Place ONE piece of markup where a block is. Magnitudes, not "done".

    The rule lives wholly in `put_into`; only the I/O around it is here.

    THE TRUNCATION FLAG IS TAKEN HERE TOO, not only by the batch swap. Without
    `torn=` a single swap SILENTLY REMOVED the mark: `books apply --anchor
    p0055-b11 --file … --kind otsl` dropped the book's mark count from 14 to 13
    and `--status` said nothing. The excuse "a single swap has no observations
    alongside" was false — they lie INSIDE the book, in `assets/source/answers/`,
    and `out_dir` is passed here. With no source inside `torn_of` returns
    `None`, "nothing to say", which is not "whole".
    """
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    new_html, entry, body = put_into(
        html, anchor, fragment, kind, source, block_role(out_dir, anchor),
        torn=torn_of(observed(os.path.join(out_dir, SOURCE)).get(anchor)))
    if entry is None:
        # Silently returning "placed 0" would be a zero from not knowing: "the
        # block already carries exactly this" and "the swap failed" are
        # different answers.
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


def undo(out_dir: str, anchor: str, log=print) -> dict:
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

    # Compare WHAT IS THERE NOW against what we put there: there used to be no
    # such comparison at all, and "undo" sounds safe.
    now = swap.get(html, anchor)
    if not _same(now, rec["sha256_placed"]):
        raise SwapError(
            f"what lies at {anchor} is not what the last swap put there "
            f"(sha256 {_sha256(now)[:12]} against "
            f"{rec['sha256_placed'][:12]}). The book was edited past the "
            f"journal; an undo would erase that edit. Sort it out by hand.")

    new_html = swap.restore(html, anchor, rec["removed"])

    # COMPARE WHAT CAME BACK, not what the journal promised. There used to be
    # one `restore` line here while the journal's `sha256_removed` was printed —
    # a magnitude this command did NOT compute. Measured: replacing the removed
    # field in swaps.json with 47 characters while `sha256_removed` stayed
    # untouched gave exit code 0 and "undone to 2319ff87fc44 (47 chars)",
    # where the hash belongs to the original 192 — the command was producing
    # someone else's proof. The hash printed is the COMPUTED one.
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
        # The entry is NOT deleted: an empty stack and "this anchor was never
        # touched" are different states, and `pop` made them indistinguishable.
        # Measured: put -> undo -> status printed "the second level has not
        # walked this book yet" about a book walked twice, and the third zero
        # declared in `status` was unreachable by construction.
        j["swaps"][anchor] = []
    # The journal is written BEFORE the book: a failure on the journal (no
    # space, a read-only directory) would leave a changed book with no undo
    # record — the very state the journal exists to make impossible.
    save_journal(out_dir, j)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)

    log(f"{anchor}: undone, computed sha256 {got[:12]} "
        f"({len(back)} chars, swap of {rec['when']}); "
        f"left in the stack {len(stack)}")
    return {"anchor": anchor, "restored": len(back),
            "undo_depth": len(stack)}


def status(out_dir: str, log=print) -> dict:
    """What is swapped and what is still an image — journal COMPARED against book.

    Only the journal used to be read, and it could drift from the book silently.
    The cheapest way to split the two is our own command: `books html --out`
    into the same directory rebuilds from scratch knowing nothing of
    `swaps.json`, and the journal then claims "1 swapped" about a book holding
    the original image. The operator learned of it only at undo, as the false
    accusation "the book was edited past the journal".
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

    `books html` writes `args.detect` into `assets/run.json`, so asking the
    operator is asking twice: the book remembers what made it.

    `None` if there is no snapshot, the field is empty, or the directory is gone
    from disk. Three different "no"s deliberately NOT told apart: the caller
    needs `--from` either way and will name the reason from the path.
    """
    # THE SOURCE INSIDE THE BOOK FIRST. `books html` puts it in
    # `assets/source`, the only path that survives moving the directory to
    # another machine. The snapshot records an ABSOLUTE path, and it lies
    # exactly when the book has been copied — the commonest case.
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


def from_read(out_dir: str, read_dir: str, only_role: str = "artifact",
              log=print) -> dict:
    """Place in the book EVERYTHING the second level read. One at a time, undoable.

    THE MISSING LINK, and it was missing silently. `books read` fills `content`
    on every block, but `doc/html.py` draws an artifact as an image regardless
    of content (`if role == "artifact" or not b.content`) — RIGHT by design,
    since an artifact swap must be reversible and journalled while a rebuild
    knows nothing of the journal. The bridge was missing: read tables and
    formulas reached the book by no route at all, `otsl.to_html` called by
    nobody.

    Text blocks do NOT come here by default (`only_role="artifact"`): the build
    prints them as `<p>` on non-empty `content`, and swapping them too would
    give one block two owners.

    Returns magnitudes, not "done": placed, skipped, refused — and why refused,
    by name.
    """
    import glob as _glob

    pages = sorted(_glob.glob(os.path.join(read_dir, "pages", "*.json")))
    if not pages:
        raise SwapError(f"no pages/*.json in {read_dir} — this is not a "
                        f"`books read` directory")
    tally = {"block_count": 0, "placed": 0, "already_placed": 0,
             "nothing_to_place": 0, "wrong_bucket": 0, "refused": 0,
             "chars": 0, "impossible_table_shape": 0,
             # REWRAPPED IS NOT NEW WORK, and without this number it looks
             # like it. Measured: a book built by the old code gives "placed
             # 5" under the new `apply` — same model bytes, OUR wrapper changed
             # (marks added). "A repeat is free" holds within one edition of the
             # code; a new wrapper is a real swap and belongs on the undo stack,
             # but calling it "placed" journals work that never happened.
             "rewrapped": 0,
             # MERGES AS A MAGNITUDE, without which they are mute: that is how
             # "104 tables at colspan 0" lived through a whole run unnoticed,
             # neither journal nor snapshot nor `blocks.json` counting spans,
             # and a regression back to zero would be as invisible.
             "merges_declared": 0, "merges_in_book": 0,
             "tables_with_merges": 0}
    refused = []
    # Placed AND MARKED, listed apart: see the summary lines at the end.
    misshapen = []
    # READING OBSERVATIONS — from where the content comes. Without them the
    # truncation mark was lost on exactly the blocks that reached the reader as
    # markup: the build set 14 marks, the swap removed 4.
    obs = observed(read_dir)
    src = os.path.basename(os.path.abspath(read_dir))

    # READ AND WRITE ONCE, not per swap: `put` used to be called here, and with
    # it the quadratic reread of `put_into`. The guards are the very same ones —
    # they live there and are not repeated here by a word.
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    roles = block_roles(out_dir)
    j = load_journal(out_dir)

    for fp in pages:
        with open(fp, encoding="utf-8") as f:
            page = json.load(f)
        for b in page.get("blocks", []):
            tally["block_count"] += 1
            anchor = anchor_of(page["index"], b["block_id"])
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
                    # ONE RULE, AND IT IS CALLED. A second copy of `torn_of`
                    # stood here inline — the very thing the rule's seam exists
                    # to prevent. It collapsed three states into two ("not
                    # asked" became "finished") and, being unsubstitutable, kept
                    # the battery out of the book path entirely.
                    torn=torn_of(obs.get(anchor)))
            except SwapError as e:
                tally["refused"] += 1
                refused.append(f"{anchor}: {str(e)[:80]}")
                continue
            # COUNTED HERE, past both refusals — only then does the number
            # describe the BOOK and not this run's work. See `_count_in_book`.
            _count_in_book(tally, misshapen, anchor, body,
                            b.get("kind") or "html")
            if entry is None:            # exactly this already lies there
                tally["already_placed"] += 1
                continue
            # THE SAME MODEL BYTES UNDER A DIFFERENT WRAPPER — its own
            # magnitude. Compared by the sha of the MODEL'S ANSWER, not the
            # finished body: the body differs by exactly our wrapper, and what
            # must be compared is what was paid for on the card.
            previous = j["swaps"].get(anchor) or []
            if previous and previous[-1].get("sha256_model_answer") == \
                    entry.get("sha256_model_answer"):
                tally["rewrapped"] += 1
            j["swaps"].setdefault(anchor, []).append(entry)
            tally["placed"] += 1
            tally["chars"] += len(body)

    # Journal before book, same reason as in `undo`: break the write between
    # them and undo knows of a swap the book does not have — safer than the
    # reverse.
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
    # FOUR different zeros, each with its own cause. The fourth — "everything
    # is already there" — arrived with idempotence; before it a repeat printed
    # "not one block landed: no \"artifact\" bucket among what was read"
    # with 412 blocks standing: a talking step lying with a zero, and it
    # sounded like a verdict on the reading.
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
    # PLACED DOES NOT MEAN GOOD, its own magnitude. Printed ALWAYS, zero
    # included: a line that vanishes at zero reads as "this never happens". Of
    # 104 tables placed on "Refractory technology" one is a `<table>` with
    # 2047 cells in a single row, and "placed 412" was silent about it.
    # TWO NUMBERS, NOT ONE. Apart means the translation lost a merge the model
    # declared; together means everything it marked arrived.
    # THE WORDS "IN THE BOOK", NOT "PLACED": both lines describe the WHOLE
    # BOOK, and on a repeat run "placed 0" beside "at 2 placed" would read as
    # a contradiction.
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
    # A MARK NO CSS DRAWS IS A MARK IN THE JOURNAL ONLY. Measured: a book built
    # by the old code gets `data-truncated` and `data-table-shape` in its body
    # after `apply` while its `<style>` has no rules for them, and tables
    # collapsed into spans lose the `overflow-x` guard. We do not edit the CSS:
    # the book is the build's product, and a swap has no business in it.
    if tally["placed"] or tally["impossible_table_shape"]:
        # LOOK AT WHAT IS ALREADY READ. The first version reread the file and
        # broke the guard "the batch swap reads the book ONCE": a check for a
        # warning must not cost what it warns about.
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
