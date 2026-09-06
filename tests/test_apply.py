"""Swapping a block in a finished BOOK: files, journal, undo.

`test_swap.py` guards pure strings; here the files begin, and with them the one
thing the whole two-level scheme was started for: "a swap can be checked,
undone and redone by another model without touching the book".

The promise stands on three things, each checked here:
  * what was taken out is KEPT, else there is nothing to undo with;
  * a stack, not a last value: two swaps in a row undo one at a time, else the
    middle state vanishes silently;
  * after an undo the book matches the original BYTE FOR BYTE -- "almost
    matches" means nothing when one character in five hundred pages is
    invisible to everybody.
"""
import json
import os
import tempfile

from booksmith.doc import apply as ap
from booksmith.doc import swap

A, B = "p0042-b17", "p0042-b18"
BOOK = ("<!doctype html><html><body>\n<p>before</p>"
        + swap.wrap(A, '<figure id="p0042-b17">table picture</figure>')
        + "<p>between</p>"
        + swap.wrap(B, '<figure id="p0042-b18">figure picture</figure>')
        + "<p>tail</p>\n</body></html>\n")


def book(tmp):
    p = os.path.join(tmp, "book.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(BOOK)
    return p


def test_put_then_undo_restores_the_book_byte_for_byte():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><tr><td>1</td></tr></table>", log=lambda *_: None)
        after_put = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert after_put != BOOK, (
            "the swap did not change the book -- nothing to place")
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK, (
            "the undo returned the WRONG book. One character in five hundred "
            "pages is invisible, so the check is byte for byte")


def test_stack_unwinds_in_reverse_order():
    """Two swaps in a row -- two undo steps, not one.

    That is how the second level works: the model answered, the answer was no
    good, another model redid it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>first</table>", source="model-1", log=lambda *_: None)
        ap.put(tmp, A, "<table>second</table>", source="model-2", log=lambda *_: None)
        ap.undo(tmp, A, log=lambda *_: None)
        mid = swap.get(open(os.path.join(tmp, "book.html"), encoding="utf-8").read(), A)
        assert "first" in mid, (
            f"after one undo the first swap was expected, {mid[:60]!r} stands")
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_neighbour_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>new</table>", log=lambda *_: None)
        html = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert swap.get(html, B) == '<figure id="p0042-b18">figure picture</figure>'
        assert swap.anchors(html) == [A, B], "the book's anchor set changed"


def test_fragment_with_marks_is_refused_by_the_fragment_check():
    """A mark inside the inserted fragment is a ghost anchor.

    The trouble would surface not here but on the NEXT swap, as "opening marks
    2" about another block, with the book already half re-marked.

    There are TWO guards for it and the check demands the FIRST. The second --
    comparing the anchor set after the swap -- catches the same fragment, so
    replacing the first with a stub passed the battery unnoticed: the check
    went red by another's merit. It must be caught at the source, before the
    book is read at all: only there is it visible that the FRAGMENT is at
    fault.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, swap.wrap("p0001-b1", "alien"),
                   log=lambda *_: None)
        except ap.SwapError as e:
            assert "ghost anchors" in str(e), (
                f"refused, but NOT by the fragment check: {str(e)[:120]!r}")
        else:
            raise AssertionError(
                "a fragment with an alien mark was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_empty_fragment_is_refused():
    """An empty swap erases the block and looks like "the model kept quiet"."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        for empty in ("", "   \n"):
            try:
                ap.put(tmp, A, empty, log=lambda *_: None)
            except ap.SwapError:
                pass
            else:
                raise AssertionError(
                    f"the empty fragment {empty!r} was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unknown_kind_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table/>", kind="markdown", log=lambda *_: None)
        except ap.SwapError as e:
            assert "markdown" in str(e)
        else:
            raise AssertionError("an undeclared kind was accepted silently")


def test_undo_without_a_swap_is_loud_and_distinct():
    """Never swapped and undo failed are different troubles, and say so."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "was never swapped" in str(e)
        else:
            raise AssertionError("an undo without a swap passed silently")


def test_edit_outside_the_journal_blocks_undo():
    """The book was edited by hand -- a blind undo would erase that edit.

    "Undo" sounds safe, which is exactly why the check is needed: without it
    the command silently destroys somebody else's work.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = book(tmp)
        ap.put(tmp, A, "<table>answer</table>", log=lambda *_: None)
        h = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(h.replace("answer", "hand edit"))
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "past the journal" in str(e)
        else:
            raise AssertionError(
                "the undo erased an edit made past the journal")


def test_journal_keeps_what_was_taken():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>x</table>", source="probe", log=lambda *_: None)
        j = json.load(open(os.path.join(tmp, ap.JOURNAL), encoding="utf-8"))
        rec = j["swaps"][A][-1]
        assert rec["removed"] == '<figure id="p0042-b17">table picture</figure>', (
            "the journal did not keep what was removed -- there will be "
            "nothing to undo with")
        assert rec["placed_by"] == "probe" and rec["kind"] == "html"


def test_status_tells_three_zeroes_apart():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        said = []
        r = ap.status(tmp, log=said.append)
        assert r["anchor_count"] == 2 and r["swaps_total"] == 0
        assert any("has not walked this book yet" in s for s in said), (
            "\"no swaps\" and \"the book is empty\" print the same -- these "
            "are different zeros")

def test_unterminated_mark_is_caught_by_the_anchor_guard():
    """An unterminated mark passes the FRAGMENT check and is caught by ANCHORS.

    The second guard exists for this case alone: the fragment holds no complete
    mark, `_check_fragment` lets it through, and `swap.anchors` finds a closing
    `-->` further down the book and gives birth to a rubbish anchor. The check
    demands THAT guard -- take it away and it would go red by the first one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<p>text <!--bs:p0001-b9 inside</p>",
                   log=lambda *_: None)
        except ap.SwapError as e:
            assert "changed the book's anchor set" in str(e), (
                f"refused, but NOT by the anchor comparison: {str(e)[:120]!r}")
        else:
            raise AssertionError("an unterminated mark was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unclosed_comment_is_caught_by_its_own_guard():
    """An unclosed comment eats the block's closing mark.

    The FIFTH guard, raised because the four before it let this through, every
    one: the fragment carries no block marks, is not empty, its kind is
    declared, and the anchor set does NOT change -- `swap.anchors` looks for
    `<!--bs:`, and a bare `<!--` is no anchor to it. Measured before the fix on
    a book of 26 blocks: the command answered "placed 154, taken 175, anchors
    26", while by the VISIBLE markup (once the browser has eaten the comments)
    div went open 0 -> 1, closed 0 -> 0, figure 26 -> 25 -- the rest of the
    book inside an unclosed div.

    The check demands THIS guard: the anchor comparison is silent here by
    construction.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table><tr><td>1</td></tr></table>"
                           "<!-- did not finish", log=lambda *_: None)
        except ap.SwapError as e:
            assert "a comment is opened and not closed" in str(e), (
                f"refused, but NOT by the comment guard: {str(e)[:120]!r}")
        else:
            raise AssertionError("an unfinished comment was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_a_closed_comment_is_not_refused():
    """A guard must be able NOT to fire as well: a closed comment is lawful.

    Without this half the check is green from forbidding everything, and the
    second level may lawfully return markup with a comment inside.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><!-- totals row --><tr><td>1</td></tr></table>",
               log=lambda *_: None)
        h = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert "<!-- totals row -->" in h, "a lawful comment did not arrive"
        # And escaped kinds get no false refusal: `render` for `text`/`latex`/
        # `otsl` turns `<` into `&lt;`, so there is no comment there.
        ap.put(tmp, B, "total <!-- this is text, not a comment", kind="text",
               log=lambda *_: None)


def test_a_broken_journal_is_not_an_empty_journal():
    """An unreadable journal must stop the work, not pretend to be empty.

    The temptation to return `{"swaps": {}}` would cost the whole book: the
    next swap would write its one record over the stump and the undo stack of
    ALL previous swaps would vanish silently. Also checked: the stump is left
    on disk untouched -- it will be repaired by hand.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>first</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(whole[:len(whole) // 2])          # a broken write
        stump = open(p, encoding="utf-8").read()
        try:
            ap.put(tmp, B, "<table>second</table>", log=lambda *_: None)
        except ap.SwapError as e:
            assert "does not read as json" in str(e), (
                f"refused, but not for an unreadable journal: "
                f"{str(e)[:120]!r}")
        else:
            raise AssertionError(
                "a swap over an unreadable journal went through -- the undo "
                "stack of the whole book was silently overwritten")
        assert open(p, encoding="utf-8").read() == stump, (
            "the journal stump was rewritten, and it holds the only trace "
            "of the earlier swaps")


def test_journal_is_written_atomically():
    """A broken journal write may not erase the undo stack of the whole book.

    `open(p, "w")` truncates the old file FIRST, and whatever happens next
    leaves a stump in its place. Measured on a journal of three swaps (2101
    bytes): the old way left 1076 bytes on disk, unreadable as json; the
    present one leaves the journal whole and the stump in `swaps.json.tmp`.
    """
    import json as _json

    class Boom(RuntimeError):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        for i in range(3):
            ap.put(tmp, A, f"<table>variant {i}</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()

        def half(obj, f, **kw):
            s = _json.dumps(obj, ensure_ascii=False, indent=1)
            f.write(s[:len(s) // 2])
            raise Boom("the write broken midway")

        j = ap.load_journal(tmp)
        j["swaps"]["p9999-b9"] = [{"junk": "x"}]
        real, _json.dump = _json.dump, half
        try:
            ap.save_journal(tmp, j)
        except Boom:
            pass
        else:
            raise AssertionError(
                "the substitution did not fire -- the measurement measured "
                "nothing")
        finally:
            _json.dump = real
        assert open(p, encoding="utf-8").read() == whole, (
            "the broken write erased the journal: the undo stack of the whole "
            "book is lost")
        assert len(ap.load_journal(tmp)["swaps"][A]) == 3, "the stack shrank"


def _bulk_stand(tmp, blocks=6):
    """A book of N blocks and a reading directory for it."""
    with open(os.path.join(tmp, "book.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>\n" + "\n".join(
            swap.wrap(f"p0000-b{i}",
                      f'<figure id="p0000-b{i}">picture</figure>')
            for i in range(blocks)) + "\n</body></html>\n")
    # What is observed on the side lies in the KITCHEN (`assets/`): the root of
    # a build holds one file. The path is asked of the module rather than typed
    # as a string -- else the fixture drifts from the builder silently.
    os.makedirs(os.path.join(tmp, ap.ASSETS), exist_ok=True)
    with open(os.path.join(tmp, ap.ASSETS, "blocks.json"), "w",
              encoding="utf-8") as f:
        json.dump({f"p0000-b{i}": {"role": "artifact"} for i in range(blocks)}, f)
    os.makedirs(os.path.join(tmp, "read", "pages"))
    with open(os.path.join(tmp, "read", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        json.dump({"index": 0, "blocks": [
            {"block_id": i, "kind": "html",
             "content": f"<table><tr><td>{i}</td></tr></table>"}
            for i in range(blocks)]}, f)


def test_bulk_reads_the_book_once_not_once_per_block():
    """A bulk swap reads the book ONCE, not once per block.

    What it cost: `from_read` called `put` per swap, and `put` re-read the
    whole book and parsed ALL its anchors twice; `block_role` re-read
    `blocks.json` per block. Measured on "Refractory technology" (2.3 MB, 6156
    blocks, 412 swaps): 363 seconds against 5 after the fix, several gigabytes
    of reading. The bodies matched byte for byte afterwards, and the journal
    too -- 412 anchors with the same hashes.

    FILE OPENINGS are counted, not time: time measures the machine, openings
    the design. It can fail: put `put` back inside the loop.
    """
    import builtins

    with tempfile.TemporaryDirectory() as tmp:
        _bulk_stand(tmp, blocks=6)
        counted = {"book": 0, "blocks": 0}
        was = builtins.open

        def counter(f, *a, **kw):
            name = os.path.basename(str(f))
            mode = (a[0] if a else kw.get("mode", "r"))
            if "r" in mode and "w" not in mode:
                if name == "book.html":
                    counted["book"] += 1
                elif name == "blocks.json":
                    counted["blocks"] += 1
            return was(f, *a, **kw)

        builtins.open = counter
        try:
            res = ap.from_read(tmp, os.path.join(tmp, "read"),
                               log=lambda *_: None)
        finally:
            builtins.open = was

    assert res["placed"] == 6, f"placed {res['placed']} of 6"
    assert counted["book"] == 1, (
        f"the book was read {counted['book']} times for 6 swaps -- the rule "
        f"is fused with the I/O again, and on six thousand blocks that is "
        f"six minutes")
    assert counted["blocks"] <= 1, (
        f"blocks.json was read {counted['blocks']} times -- roles are taken "
        f"one at a time instead of one read for the whole book")


def test_bulk_and_single_put_agree_block_for_block():
    """The bulk swap and the single one give ONE AND THE SAME book.

    A speed-up must be only a speed-up. Checked the way the real book was:
    bodies compared byte for byte.
    """
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        _bulk_stand(t1)
        _bulk_stand(t2)
        ap.from_read(t1, os.path.join(t1, "read"), log=lambda *_: None)
        for i in range(6):
            ap.put(t2, f"p0000-b{i}",
                   f"<table><tr><td>{i}</td></tr></table>",
                   source="read", log=lambda *_: None)
        a = open(os.path.join(t1, "book.html"), encoding="utf-8").read()
        b = open(os.path.join(t2, "book.html"), encoding="utf-8").read()
    assert a == b, "the bulk and the single swap gave DIFFERENT books"


def test_putting_the_same_markup_twice_changes_nothing():
    """A REPEAT IS NOT WORK: the book untouched, the undo stack no taller.

    WHAT IT COST. Before this check a second `books apply` put everything
    again: the content did not change and the journal doubled -- on "Refractory
    technology" 412 swaps became 824 and the depth of EVERY stack became two.
    `--undo` would then take two calls to get the picture back, and "how many
    times the book was built" became indistinguishable from "how many times the
    block was redone". It also makes the default safe: typing `books apply
    book` twice breaks nothing.

    A repeat is a body that matched COMPLETELY -- kind, source and role
    included. The same fragment from another model is work and it passes:
    checked below.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        first = ap.put(tmp, A, "<p>one</p>", kind="html", source="m1",
                        log=lambda *_: None)
        snapshot = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()

        second = ap.put(tmp, A, "<p>one</p>", kind="html", source="m1",
                        log=lambda *_: None)
        assert second.get("already_placed") is True, (
            f"the repeat was not recognised: {second}. It would grow the undo "
            f"stack by a step without changing the book")
        assert second["placed"] == 0, second
        assert first["undo_depth"] == second["undo_depth"] == 1, (
            f"the undo stack grew on a repeat: {first['undo_depth']} -> "
            f"{second['undo_depth']}")
        now = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert now == snapshot, (
            "the book changed under a repeat of the same swap")

        # And ANOTHER source is work, the stack must grow: else a block could
        # no longer be redone by another model.
        third = ap.put(tmp, A, "<p>one</p>", kind="html", source="m2",
                        log=lambda *_: None)
        assert third["undo_depth"] == 2, (
            f"a swap from another source did not land: {third}. A repeat is a "
            f"match of the BODY, and the body carries the source too")


def test_the_source_inside_the_book_beats_the_recorded_path():
    """The source INSIDE the book beats the path from the snapshot.

    The snapshot records an ABSOLUTE path, which lies in the commonest case of
    all -- the book copied to another machine, or the reading directory moved.
    `books html` puts the source into `assets/source`, and it travels with the
    book.

    WHAT IT COST. The book directory held everything to READ the book and not
    everything to REBUILD it: `blocks.json` carries box, label, order and role,
    but no `content`. The read text lived only as markup in `book.html` and in
    a foreign directory paid for on the card -- delete that and the book takes
    a new rental to assemble (915 078 characters, $0.545).
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        os.makedirs(os.path.join(tmp, ap.ASSETS), exist_ok=True)
        # The snapshot holds a path that is NOT on disk.
        with open(os.path.join(tmp, ap.ASSETS, "run.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"args": {"detect": "/no/such/directory"}}, f,
                      ensure_ascii=False)
        assert ap.source_of(tmp) is None, (
            "the path from the snapshot was accepted though the directory "
            "is gone -- the command would fall inside instead of refusing")

        own = os.path.join(tmp, ap.SOURCE, "pages")
        os.makedirs(own)
        assert ap.source_of(tmp) == os.path.join(tmp, ap.SOURCE), (
            f"the source inside the book was not found: "
            f"{ap.source_of(tmp)!r}. A book moved to another machine would "
            f"stop assembling")


def test_the_book_remembers_where_it_was_built_from():
    """`books apply` with no keys takes the source from the book's snapshot.

    Nothing to ask twice: `books html` wrote the path into `assets/run.json`,
    and a man who types `books apply book` may expect it to assemble. No
    snapshot, or the directory gone -- `None`, said out loud rather than
    placing nothing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        assert ap.source_of(tmp) is None, (
            "a source was found where there is no snapshot at all -- the "
            "command would go placing who knows what")

        reading = os.path.join(tmp, "read")
        os.makedirs(os.path.join(reading, "pages"))
        os.makedirs(os.path.join(tmp, ap.ASSETS), exist_ok=True)
        with open(os.path.join(tmp, ap.ASSETS, "run.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"args": {"detect": reading}}, f, ensure_ascii=False)
        assert ap.source_of(tmp) == reading, (
            f"the source from the snapshot was not read: "
            f"{ap.source_of(tmp)!r}")

        # Gone directory and empty snapshot both give None -- but the refusal
        # names the path.
        os.rmdir(os.path.join(reading, "pages"))
        assert ap.source_of(tmp) is None, (
            "a vanished reading directory was passed off as a source -- the "
            "command would fall inside instead of refusing")


def test_a_journal_from_the_old_layout_is_seen_not_declared_empty():
    """A journal in the book's ROOT is read, not declared "no swaps at all".

    WHAT IT COST. The journal moved into `assets/`, and books built before the
    move keep it in the root. Not noticing, the command answered "the second
    level has not walked this book yet" where the undo stack of all the paid
    work lay: 412 swaps on `vl-reads/ruall.read/html`, 17 on `ru20.read/html`.
    A zero from misunderstanding, on data that cost money. The second half is
    worse: the next swap would start a SECOND journal in `assets/` and the
    first would be unreachable. So we write BACK WHERE WE READ, checked here
    too.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<p>one</p>", kind="html", source="m1",
               log=lambda *_: None)
        new = os.path.join(tmp, ap.JOURNAL)
        assert os.path.exists(new), (
            "the journal is not in the kitchen -- the edit did not apply")

        # Move the journal to the root: that is a book of the old layout.
        old = os.path.join(tmp, "swaps.json")
        os.replace(new, old)
        j = ap.load_journal(tmp)
        assert len(j["swaps"]) == 1, (
            f"the journal in the root was not read: {j['swaps']}. The book "
            f"would declare itself untouched while holding an undo stack")

        # The second swap must land IN THE SAME file, not start a second one.
        ap.put(tmp, B, "<p>two</p>", kind="html", source="m1",
               log=lambda *_: None)
        assert not os.path.exists(new), (
            "a SECOND journal was started in the kitchen while a live one "
            "lies in the root -- the undo stack has split across two files")
        assert len(ap.load_journal(tmp)["swaps"]) == 2, (
            "the second swap did not land in the journal that was read")
