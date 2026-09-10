"""Swapping a block in a finished book: files, journal, undo.

`test_swap.py` guards pure strings; here the files begin, and with them the
thing the two-level scheme was started for: a swap can be checked, undone and
redone by another model without touching the book. That stands on three
properties, each checked here -- what was taken out is kept, the journal is a
stack rather than a last value, and after an undo the book matches the original
byte for byte.
"""
import json
import os
import tempfile

from booksmith.core.book import JOURNAL
from booksmith.processing.assemble import apply as ap
from booksmith.processing.assemble import swap
import support

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
        ap.put(tmp, A, "<table><tr><td>1</td></tr></table>")
        after_put = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert after_put != BOOK, (
            "the swap did not change the book -- nothing to place")
        ap.undo(tmp, A)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK, (
            "the undo returned the WRONG book. One character in five hundred "
            "pages is invisible, so the check is byte for byte")


def test_stack_unwinds_in_reverse_order():
    """Two swaps in a row -- two undo steps, not one: the model answered, the
    answer was no good, another model redid it."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>first</table>", source="model-1")
        ap.put(tmp, A, "<table>second</table>", source="model-2")
        ap.undo(tmp, A)
        mid = swap.get(open(os.path.join(tmp, "book.html"), encoding="utf-8").read(), A)
        assert "first" in mid, (
            f"after one undo the first swap was expected, {mid[:60]!r} stands")
        ap.undo(tmp, A)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_neighbour_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>new</table>")
        html = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert swap.get(html, B) == '<figure id="p0042-b18">figure picture</figure>'
        assert swap.anchors(html) == [A, B], "the book's anchor set changed"


def test_fragment_with_marks_is_refused_by_the_fragment_check():
    """A mark inside the inserted fragment is a ghost anchor, and the check
    demands the first of the two guards: caught at the source, before the book is
    read, is the only place where the fragment itself is visibly at fault."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, swap.wrap("p0001-b1", "alien"))
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
                ap.put(tmp, A, empty)
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
            ap.put(tmp, A, "<table/>", kind="markdown")
        except ap.SwapError as e:
            assert "markdown" in str(e)
        else:
            raise AssertionError("an undeclared kind was accepted silently")


def test_undo_without_a_swap_is_loud_and_distinct():
    """Never swapped and undo failed are different troubles, and say so."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.undo(tmp, A)
        except ap.SwapError as e:
            assert "was never swapped" in str(e)
        else:
            raise AssertionError("an undo without a swap passed silently")


def test_edit_outside_the_journal_blocks_undo():
    """The book was edited by hand -- a blind undo would erase that edit. "Undo"
    sounds safe, which is exactly why the check is needed."""
    with tempfile.TemporaryDirectory() as tmp:
        p = book(tmp)
        ap.put(tmp, A, "<table>answer</table>")
        h = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(h.replace("answer", "hand edit"))
        try:
            ap.undo(tmp, A)
        except ap.SwapError as e:
            assert "past the journal" in str(e)
        else:
            raise AssertionError(
                "the undo erased an edit made past the journal")


def test_journal_keeps_what_was_taken():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>x</table>", source="probe")
        j = json.load(open(os.path.join(tmp, JOURNAL), encoding="utf-8"))
        rec = j["swaps"][A][-1]
        assert rec["removed"] == '<figure id="p0042-b17">table picture</figure>', (
            "the journal did not keep what was removed -- there will be "
            "nothing to undo with")
        assert rec["placed_by"] == "probe" and rec["kind"] == "html"


def test_status_tells_three_zeroes_apart():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        with support.said() as said:
            r = ap.status(tmp)
        assert r["anchor_count"] == 2 and r["swaps_total"] == 0
        assert any("has not walked this book yet" in s for s in said), (
            "\"no swaps\" and \"the book is empty\" print the same -- these "
            "are different zeros")

def test_unterminated_mark_is_caught_by_the_anchor_guard():
    """An unterminated mark passes the fragment check and is caught by anchors:
    the fragment holds no complete mark, and `swap.anchors` finds a closing `-->`
    further down the book and gives birth to a rubbish anchor."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<p>text <!--bs:p0001-b9 inside</p>")
        except ap.SwapError as e:
            assert "changed the book's anchor set" in str(e), (
                f"refused, but NOT by the anchor comparison: {str(e)[:120]!r}")
        else:
            raise AssertionError("an unterminated mark was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unclosed_comment_is_caught_by_its_own_guard():
    """An unclosed comment eats the block's closing mark: it carries no block
    marks, is not empty, declares its kind and changes no anchor -- `swap.anchors`
    looks for `<!--bs:` -- so it needs a guard of its own."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table><tr><td>1</td></tr></table>"
                           "<!-- did not finish")
        except ap.SwapError as e:
            assert "a comment is opened and not closed" in str(e), (
                f"refused, but NOT by the comment guard: {str(e)[:120]!r}")
        else:
            raise AssertionError("an unfinished comment was accepted silently")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_a_closed_comment_is_not_refused():
    """A guard must be able not to fire as well: a closed comment is lawful, and
    the second level may return markup with a comment inside."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><!-- totals row --><tr><td>1</td></tr></table>")
        h = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert "<!-- totals row -->" in h, "a lawful comment did not arrive"
        # And escaped kinds get no false refusal: `render` for `text`/`latex`/
        # `otsl` turns `<` into `&lt;`, so there is no comment there.
        ap.put(tmp, B, "total <!-- this is text, not a comment", kind="text")


def test_a_broken_journal_is_not_an_empty_journal():
    """An unreadable journal stops the work rather than pretending to be empty:
    returning `{"swaps": {}}` would let the next swap write over the stump and
    lose every undo stack. The stump is left on disk untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>first</table>")
        p = os.path.join(tmp, JOURNAL)
        whole = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(whole[:len(whole) // 2])          # a broken write
        stump = open(p, encoding="utf-8").read()
        try:
            ap.put(tmp, B, "<table>second</table>")
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
    """A broken journal write may not erase the undo stack of the whole book:
    `open(p, "w")` truncates the old file first, so the write goes aside and a
    broken one leaves the stump in `swaps.json.tmp`."""
    import json as _json

    class Boom(RuntimeError):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        for i in range(3):
            ap.put(tmp, A, f"<table>variant {i}</table>")
        p = os.path.join(tmp, JOURNAL)
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
    # What is observed lies in the kitchen (`assets/`): the root of a build holds
    # one file. The path is asked of the module rather than typed as a string.
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
    """A bulk swap reads the book once, not once per block: `put` per swap re-read
    the whole book and parsed all its anchors twice. File openings are counted,
    not time -- time measures the machine, openings the design."""
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
            res = ap.from_read(tmp, os.path.join(tmp, "read"))
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
    """The bulk swap and the single one give one and the same book: a speed-up
    must be only a speed-up, and the bodies are compared byte for byte."""
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        _bulk_stand(t1)
        _bulk_stand(t2)
        ap.from_read(t1, os.path.join(t1, "read"))
        for i in range(6):
            ap.put(t2, f"p0000-b{i}",
                   f"<table><tr><td>{i}</td></tr></table>",
                   source="read")
        a = open(os.path.join(t1, "book.html"), encoding="utf-8").read()
        b = open(os.path.join(t2, "book.html"), encoding="utf-8").read()
    assert a == b, "the bulk and the single swap gave DIFFERENT books"


def test_putting_the_same_markup_twice_changes_nothing():
    """A repeat is not work: the book untouched, the undo stack no taller, so
    `books apply book` twice breaks nothing. A repeat is a body that matched
    completely -- kind, source and role included."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        first = ap.put(tmp, A, "<p>one</p>", kind="html", source="m1")
        snapshot = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()

        second = ap.put(tmp, A, "<p>one</p>", kind="html", source="m1")
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
        third = ap.put(tmp, A, "<p>one</p>", kind="html", source="m2")
        assert third["undo_depth"] == 2, (
            f"a swap from another source did not land: {third}. A repeat is a "
            f"match of the BODY, and the body carries the source too")


def test_the_source_inside_the_book_beats_the_recorded_path():
    """The source inside the book beats the path from the snapshot, which is
    absolute and lies in the commonest case of all: the book copied to another
    machine, or the reading directory moved."""
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
    """`books apply` with no keys takes the source from the book's snapshot: no
    snapshot, or the directory gone, gives `None`, said out loud rather than
    placing nothing."""
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


