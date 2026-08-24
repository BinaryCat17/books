# -*- coding: utf-8 -*-
"""Второй запуск не меняет ни байта.

Требование, а не украшение: `books restructure` переписывает книгу НА МЕСТЕ, а
разбор стоит денег и не воспроизводится.  Шаг, который на втором прогоне
что-то ещё «дочищает», означает, что первый отработал не до конца, — так и
поймали, что склейка переносов не шла до неподвижности (второй прогон
находил ещё девять переносов).

Быстрый слой — стенд: 12 настоящих страниц трёх книг.
Медленный слой (`E6_SLOW=1`) — шесть настоящих книг из копии `e6/data`.
"""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

S = H.mod("structure")
M = H.mod("merge")


def свести_и_собрать(d):
    H.quiet(M.assemble, d)
    H.quiet(S.restructure, d)


def слепок(d, только=None):
    return {os.path.basename(f): H.digest(f) for f in H.book_files(d)
            if только is None or (os.path.basename(f) in только)
            or (только == "книга" and not os.path.basename(f).startswith("report"))}


КНИГА_И_ОГЛАВЛЕНИЕ = "книга"
ОТЧЁТ_ПЛЫВЁТ = []


class ПовторБезИзменений(unittest.TestCase):
    maxDiff = None

    # ---- быстрый слой -----------------------------------------------------
    def test_restructure_книга_и_оглавление(self):
        """Книга и оглавление обязаны быть байт в байт — это заявлено в CLAUDE.md."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    H.quiet(M.assemble, d)
                    H.quiet(S.restructure, d)
                    было = слепок(d, КНИГА_И_ОГЛАВЛЕНИЕ)
                    H.quiet(S.restructure, d)
                    self.assertEqual(было, слепок(d, КНИГА_И_ОГЛАВЛЕНИЕ),
                                     "второй restructure изменил книгу")
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_restructure_отчёт(self):
        """Отчёт — тоже прибор, и он обязан говорить про КНИГУ, а не про запуск.

        На нынешнем коде красный: второй прогон пишет «склеено переносов: 0»
        про книгу, где склеено 4.  Ноль-от-повтора неотличим от
        ноля-от-нечего-склеивать — ровно тот порок отчёта, который называет Э4.
        """
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    H.quiet(M.assemble, d)
                    H.quiet(S.restructure, d)
                    было = слепок(d, ("report.md",))
                    H.quiet(S.restructure, d)
                    self.assertEqual(было, слепок(d, ("report.md",)),
                                     "второй restructure переписал отчёт")
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_merge_на_стенде(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    H.quiet(M.assemble, d)
                    было = слепок(d)
                    H.quiet(M.assemble, d)
                    self.assertEqual(было, слепок(d), "второй merge изменил файлы")
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_merge_после_restructure_не_ломает_книгу(self):
        """Порядок, в котором это и делают: свод, структура, снова свод."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    свести_и_собрать(d)
                    было = слепок(d)
                    свести_и_собрать(d)
                    self.assertEqual(было, слепок(d))
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_mark_prose_неподвижна(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = os.path.join(H.STAND, b, "passes")
                base = H.read(os.path.join(d, "1", "book", "book.md"))
                wit = [H.read(os.path.join(d, k, "book", "book.md"))
                       for k in sorted(os.listdir(d)) if k != "1"]
                раз = M.mark_prose(base, wit)[0]
                два, n2, _ = M.mark_prose(раз, wit)
                self.assertEqual(раз, два, "второй свод прозы изменил текст")
                self.assertEqual(n2, 0, f"второй свод поставил ещё {n2} пометок")

    def test_mark_cells_неподвижна(self):
        """На нынешнем коде красный: `plain()` снимает `≠` перед сверкой, и
        второй свод ставит знак второй раз.  Замер на стенде: 147 -> 294 ->
        441 у chugun, 24 -> 48 -> 72 у Фейнмана, 67 -> 134 -> 201 у
        огнеупоров.  У прозы такая охрана есть (`endswith("≠") -> continue`),
        у ячеек нет."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = os.path.join(H.STAND, b, "passes")
                base = H.read(os.path.join(d, "1", "book", "book.md"))
                wit = [H.read(os.path.join(d, k, "book", "book.md"))
                       for k in sorted(os.listdir(d)) if k != "1"]
                раз = M.mark_cells(base, wit)[0]
                два = M.mark_cells(раз, wit)[0]
                self.assertEqual(раз, два, "второй свод ячеек изменил текст")

    def test_join_hyphens_неподвижна(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                t = H.read(os.path.join(H.STAND, b, "passes", "1", "book", "book.md"))
                раз, n1 = S.join_hyphens(S._protect(t)[0])
                два, n2 = S.join_hyphens(раз)
                self.assertEqual(раз, два)
                self.assertEqual(n2, 0, f"второй проход склеил ещё {n2}")

    # ---- медленный слой ---------------------------------------------------
    @unittest.skipUnless(H.SLOW, "медленно: шесть книг (E6_SLOW=1, "
                                 "сначала tools/copy_text.py)")
    def test_restructure_на_настоящих_книгах(self):
        книги = H.real_books()
        self.assertTrue(книги, "нет копии книг: python3 tools/copy_text.py")
        for d in книги:
            b = os.path.basename(d)
            with self.subTest(книга=b):
                снап = [f for f in os.listdir(d) if f.endswith(".before-restructure")]
                if снап:
                    shutil.copy(os.path.join(d, снап[0]),
                                os.path.join(d, снап[0][:-len(".before-restructure")]))
                H.quiet(S.restructure, d)
                книга = слепок(d, КНИГА_И_ОГЛАВЛЕНИЕ)
                отчёт = слепок(d, ("report.md",))
                H.quiet(S.restructure, d)
                self.assertEqual(книга, слепок(d, КНИГА_И_ОГЛАВЛЕНИЕ),
                                 "второй restructure изменил книгу")
                if отчёт != слепок(d, ("report.md",)):
                    ОТЧЁТ_ПЛЫВЁТ.append(b)


if __name__ == "__main__":
    r = unittest.main(verbosity=2, exit=False)
    if ОТЧЁТ_ПЛЫВЁТ:
        print(f"\nотчёт не идемпотентен у {len(ОТЧЁТ_ПЛЫВЁТ)} книг: "
              + ", ".join(ОТЧЁТ_ПЛЫВЁТ))
    sys.exit(0 if r.result.wasSuccessful() and not ОТЧЁТ_ПЛЫВЁТ else 1)
