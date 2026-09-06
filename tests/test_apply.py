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
BOOK = ("<!doctype html><html><body>\n<p>до</p>"
        + swap.wrap(A, '<figure id="p0042-b17">картинка таблицы</figure>')
        + "<p>между</p>"
        + swap.wrap(B, '<figure id="p0042-b18">картинка рисунка</figure>')
        + "<p>после</p>\n</body></html>\n")


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
        assert after_put != BOOK, "замена не изменила книгу — ставить нечего"
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK, (
            "откат вернул НЕ ту книгу. Разницу в один символ на пятистах "
            "страницах не увидит никто, поэтому сверка только побайтовая")


def test_stack_unwinds_in_reverse_order():
    """Two swaps in a row -- two undo steps, not one.

    That is how the second level works: the model answered, the answer was no
    good, another model redid it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>первая</table>", source="модель-1", log=lambda *_: None)
        ap.put(tmp, A, "<table>вторая</table>", source="модель-2", log=lambda *_: None)
        ap.undo(tmp, A, log=lambda *_: None)
        mid = swap.get(open(os.path.join(tmp, "book.html"), encoding="utf-8").read(), A)
        assert "первая" in mid, f"после одного отката ожидалась первая замена, а стоит {mid[:60]!r}"
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_neighbour_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>новое</table>", log=lambda *_: None)
        html = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert swap.get(html, B) == '<figure id="p0042-b18">картинка рисунка</figure>'
        assert swap.anchors(html) == [A, B], "набор якорей книги изменился"


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
            ap.put(tmp, A, swap.wrap("p0001-b1", "чужое"), log=lambda *_: None)
        except ap.SwapError as e:
            assert "призрачными якорями" in str(e), (
                f"кусок отвергнут, но НЕ проверкой куска: {str(e)[:120]!r}")
        else:
            raise AssertionError("кусок с чужой меткой принят молча")
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
                raise AssertionError(f"пустой кусок {empty!r} принят молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unknown_kind_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table/>", kind="markdown", log=lambda *_: None)
        except ap.SwapError as e:
            assert "markdown" in str(e)
        else:
            raise AssertionError("незаявленный вид принят молча")


def test_undo_without_a_swap_is_loud_and_distinct():
    """Never swapped and undo failed are different troubles, and say so."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "ни разу не заменяли" in str(e)
        else:
            raise AssertionError("откат без замены прошёл молча")


def test_edit_outside_the_journal_blocks_undo():
    """The book was edited by hand -- a blind undo would erase that edit.

    "Undo" sounds safe, which is exactly why the check is needed: without it
    the command silently destroys somebody else's work.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = book(tmp)
        ap.put(tmp, A, "<table>ответ</table>", log=lambda *_: None)
        h = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(h.replace("ответ", "правка руками"))
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "мимо журнала" in str(e)
        else:
            raise AssertionError("откат затёр правку, сделанную мимо журнала")


def test_journal_keeps_what_was_taken():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>x</table>", source="проба", log=lambda *_: None)
        j = json.load(open(os.path.join(tmp, ap.JOURNAL), encoding="utf-8"))
        rec = j["swaps"][A][-1]
        assert rec["removed"] == '<figure id="p0042-b17">картинка таблицы</figure>', (
            "журнал не сохранил снятое — откатывать будет нечем")
        assert rec["placed_by"] == "проба" and rec["kind"] == "html"


def test_status_tells_three_zeroes_apart():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        said = []
        r = ap.status(tmp, log=said.append)
        assert r["anchor_count"] == 2 and r["swaps_total"] == 0
        assert any("ещё не ходил" in s for s in said), (
            "«замен нет» и «книга пуста» напечатаны одинаково — это разные нули")

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
            ap.put(tmp, A, "<p>текст <!--bs:p0001-b9 внутри</p>",
                   log=lambda *_: None)
        except ap.SwapError as e:
            assert "изменила набор якорей" in str(e), (
                f"отвергнуто, но НЕ сверкой якорей: {str(e)[:120]!r}")
        else:
            raise AssertionError("незакрытая метка принята молча")
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
                           "<!-- дальше не дописала", log=lambda *_: None)
        except ap.SwapError as e:
            assert "комментарий открыт и не закрыт" in str(e), (
                f"отвергнуто, но НЕ сторожем комментариев: {str(e)[:120]!r}")
        else:
            raise AssertionError("незавершённый комментарий принят молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_a_closed_comment_is_not_refused():
    """A guard must be able NOT to fire as well: a closed comment is lawful.

    Without this half the check is green from forbidding everything, and the
    second level may lawfully return markup with a comment inside.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><!-- строка итогов --><tr><td>1</td></tr></table>",
               log=lambda *_: None)
        h = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert "<!-- строка итогов -->" in h, "законный комментарий не доехал"
        # And escaped kinds get no false refusal: `render` for `text`/`latex`/
        # `otsl` turns `<` into `&lt;`, so there is no comment there.
        ap.put(tmp, B, "итог <!-- это текст, а не комментарий", kind="text",
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
        ap.put(tmp, A, "<table>первая</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(whole[:len(whole) // 2])          # a broken write
        stump = open(p, encoding="utf-8").read()
        try:
            ap.put(tmp, B, "<table>вторая</table>", log=lambda *_: None)
        except ap.SwapError as e:
            assert "не читается как json" in str(e), (
                f"отвергнуто, но не по причине нечитаемого журнала: {str(e)[:120]!r}")
        else:
            raise AssertionError(
                "замена по нечитаемому журналу прошла — стопка отката всей "
                "книги затёрта молча")
        assert open(p, encoding="utf-8").read() == stump, (
            "огрызок журнала переписан, а в нём единственный след прежних замен")


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
            ap.put(tmp, A, f"<table>вариант {i}</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()

        def half(obj, f, **kw):
            s = _json.dumps(obj, ensure_ascii=False, indent=1)
            f.write(s[:len(s) // 2])
            raise Boom("обрыв записи посередине")

        j = ap.load_journal(tmp)
        j["swaps"]["p9999-b9"] = [{"junk": "x"}]
        real, _json.dump = _json.dump, half
        try:
            ap.save_journal(tmp, j)
        except Boom:
            pass
        else:
            raise AssertionError("подмена не сработала — замер ничего не мерил")
        finally:
            _json.dump = real
        assert open(p, encoding="utf-8").read() == whole, (
            "оборванная запись затёрла журнал: стопка отката всей книги "
            "потеряна")
        assert len(ap.load_journal(tmp)["swaps"][A]) == 3, "стопка укоротилась"


def _bulk_stand(tmp, blocks=6):
    """A book of N blocks and a reading directory for it."""
    with open(os.path.join(tmp, "book.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>\n" + "\n".join(
            swap.wrap(f"p0000-b{i}",
                      f'<figure id="p0000-b{i}">картинка</figure>')
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

    assert res["placed"] == 6, f"поставлено {res['placed']} из 6"
    assert counted["book"] == 1, (
        f"книга прочитана {counted['book']} раз на 6 замен — правило снова "
        f"слито с вводом-выводом, и на шести тысячах блоков это шесть минут")
    assert counted["blocks"] <= 1, (
        f"blocks.json прочитан {counted['blocks']} раз — разряды берутся по "
        f"одному вместо одного чтения на всю книгу")


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
    assert a == b, "пакетная и одиночная замена дали РАЗНЫЕ книги"


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
        first = ap.put(tmp, A, "<p>раз</p>", kind="html", source="м1",
                        log=lambda *_: None)
        snapshot = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()

        second = ap.put(tmp, A, "<p>раз</p>", kind="html", source="м1",
                        log=lambda *_: None)
        assert second.get("already_placed") is True, (
            f"повтор не опознан: {second}. Он вырастит стопку отката на "
            f"ступень, не изменив книги")
        assert second["placed"] == 0, second
        assert first["undo_depth"] == second["undo_depth"] == 1, (
            f"стопка отката выросла с повтором: {first['undo_depth']} -> "
            f"{second['undo_depth']}")
        now = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert now == snapshot, "книга изменилась от повторной той же замены"

        # And ANOTHER source is work, the stack must grow: else a block could
        # no longer be redone by another model.
        third = ap.put(tmp, A, "<p>раз</p>", kind="html", source="м2",
                        log=lambda *_: None)
        assert third["undo_depth"] == 2, (
            f"замена от другого источника не встала: {third}. Повтором "
            f"считается совпадение ТЕЛА, а тело несёт и источник")


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
            json.dump({"args": {"detect": "/нет/такого/каталога"}}, f,
                      ensure_ascii=False)
        assert ap.source_of(tmp) is None, (
            "путь из слепка принят, хотя каталога нет — команда упала бы "
            "внутри вместо внятного отказа")

        own = os.path.join(tmp, ap.SOURCE, "pages")
        os.makedirs(own)
        assert ap.source_of(tmp) == os.path.join(tmp, ap.SOURCE), (
            f"источник внутри книги не найден: {ap.source_of(tmp)!r}. Книга, "
            f"перенесённая на другую машину, перестанет собираться")


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
            "источник найден там, где слепка нет вовсе — команда пошла бы "
            "ставить неизвестно что")

        reading = os.path.join(tmp, "read")
        os.makedirs(os.path.join(reading, "pages"))
        os.makedirs(os.path.join(tmp, ap.ASSETS), exist_ok=True)
        with open(os.path.join(tmp, ap.ASSETS, "run.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"args": {"detect": reading}}, f, ensure_ascii=False)
        assert ap.source_of(tmp) == reading, (
            f"источник из слепка не прочитан: {ap.source_of(tmp)!r}")

        # Gone directory and empty snapshot both give None -- but the refusal
        # names the path.
        os.rmdir(os.path.join(reading, "pages"))
        assert ap.source_of(tmp) is None, (
            "исчезнувший каталог чтения выдан за источник — команда упала бы "
            "внутри, вместо внятного отказа")


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
        ap.put(tmp, A, "<p>раз</p>", kind="html", source="м1",
               log=lambda *_: None)
        new = os.path.join(tmp, ap.JOURNAL)
        assert os.path.exists(new), "журнал не в кухне — правка не применилась"

        # Move the journal to the root: that is a book of the old layout.
        old = os.path.join(tmp, "swaps.json")
        os.replace(new, old)
        j = ap.load_journal(tmp)
        assert len(j["swaps"]) == 1, (
            f"журнал из корня не прочитан: {j['swaps']}. Книга объявила бы "
            f"себя нетронутой, имея стопку отката")

        # The second swap must land IN THE SAME file, not start a second one.
        ap.put(tmp, B, "<p>два</p>", kind="html", source="м1",
               log=lambda *_: None)
        assert not os.path.exists(new), (
            "заведён ВТОРОЙ журнал в кухне при живом журнале в корне — "
            "стопка отката разъехалась по двум файлам")
        assert len(ap.load_journal(tmp)["swaps"]) == 2, (
            "вторая замена не попала в прочитанный журнал")
