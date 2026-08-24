# -*- coding: utf-8 -*-
"""Ни одна правка не имеет права уменьшить содержимое книги.

Величины и их единицы: таблица, ячейка, тег картинки, слово, пометка `⚠`.
Слово — одно определение на весь набор (`harness.counts`): смешение
определений слова уже трижды портило выводы в этом проекте.

Убыль не запрещена совсем — она обязана быть НАЗВАНА счётчиком шага.
Склейка переноса законно уменьшает число слов ровно на число склеек: замер на
стенде, нынешний код — chugun −4 при 4 склейках, ogneupory −15 при 15.
Всё, что сверх этого, — потеря.
"""
import os, re, shutil, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

S = H.mod("structure")
M = H.mod("merge")
L = H.mod("layout")
СТРОГО = ("таблиц", "ячеек", "тегов картинок", "⚠")


def счётчики(лог):
    d = {}
    for l in лог.split("\n"):
        if l.startswith("  ") and ": " in l and not l.strip().startswith("метка"):
            k, v = l.strip().split(": ", 1)
            if v.isdigit():
                d[k] = int(v)
    return d


class НеУбыло(unittest.TestCase):

    def проверить(self, b, до, после, склеек):
        for k in СТРОГО:
            self.assertGreaterEqual(после[k], до[k],
                                    f"{b}: {k} {до[k]} -> {после[k]}")
        self.assertGreaterEqual(
            после["слов"], до["слов"] - склеек,
            f"{b}: слов {до['слов']} -> {после['слов']} при {склеек} склейках "
            f"— убыло на {до['слов'] - после['слов'] - склеек} сверх названного")

    def test_сборка_структуры_ничего_не_теряет(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    H.quiet(M.assemble, d)
                    p = L.Paths(d)
                    до = H.counts(H.read(p.snapshot))
                    _, лог = H.quiet(S.restructure, d)
                    после = H.counts(H.read(p.book))
                    self.проверить(b, до, после,
                                   счётчики(лог).get("склеено переносов", 0))
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_свод_ничего_не_теряет_против_основы(self):
        """Свод не теряет ТЕКСТА против выбранной им основы.

        Прежде здесь стояло `⚠ после >= ⚠ до` — и набор краснел на стенде
        chugun (40 -> 35).  Формулировка была неверна, а код цел: это инвариант
        ТЕКСТОСОХРАНЯЮЩЕГО шага, применённый к единственному шагу, который
        текст ЗАМЕЩАЕТ.  `⚠` — свойство одного чтения: её ставит распознаватель
        по вероятностям своих токенов, и перенести её на слова свидетеля
        нечем.  Требовать «не убыло» значит требовать, чтобы у свидетеля
        пометок было не меньше, — а это свойство данных, а не кода.

        Обратное утверждение («по книге растут во всех шести», 2 205 -> 2 541)
        тоже не инвариант, а наблюдение о сегодняшних шести книгах.

        Поэтому здесь остаётся то, что нарушить может только ошибка в коде:
        текст, таблицы, ячейки, картинки.  Счёт `⚠` вынесен в И3 —
        обязанность НАЗВАТЬ сальдо, а не удержать его знак; свод его печатает
        (потеряно 65, прибавлено 402, страниц без `⚠` 10 из 211 подменённых).
        Равенство `⚠` для текстосохраняющих шагов проверяет И1 —
        `test_idempotent` и мутация М5.
        """
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    до = H.counts(H.read(os.path.join(
                        d, "passes", "1", "book", "book.md")))
                    H.quiet(M.assemble, d)
                    после = H.counts(H.read(L.Paths(d).book))
                    for k in ("таблиц", "ячеек", "тегов картинок", "слов"):
                        self.assertGreaterEqual(
                            после[k], до[k],
                            f"{b}: {k} убыло {до[k]} -> {после[k]}")
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_ни_одна_ссылка_на_картинку_не_повисла(self):
        """Свидетель без картинок не должен приводить в книгу битые ссылки."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d = H.stand_copy(b)
                try:
                    H.quiet(M.assemble, d)
                    t = H.read(L.Paths(d).book)
                    битые = [x for x in re.findall(r'src="(imgs/[^"]+)"', t)
                             if not os.path.exists(os.path.join(d, x))]
                    self.assertFalse(битые, f"{len(битые)} битых, первая: "
                                            f"{битые[0] if битые else ''}")
                finally:
                    shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_таблицы_переживают_защиту_и_возврат(self):
        """`_protect`/`_restore` обязаны быть обратны друг другу байт в байт."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                t = H.read(os.path.join(H.STAND, b, "passes", "1", "book", "book.md"))
                тело, cпрятано = S._protect(t)
                self.assertEqual(S._restore(тело, cпрятано), t)
                self.assertEqual(len(cпрятано), len(M.TABLE.findall(t)))

    @unittest.skipUnless(H.SLOW, "медленно: шесть книг (E6_SLOW=1)")
    def test_на_настоящих_книгах(self):
        книги = H.real_books()
        self.assertTrue(книги, "нет копии книг: python3 tools/copy_text.py")
        for d in книги:
            b = os.path.basename(d)
            with self.subTest(книга=b):
                снап = [f for f in os.listdir(d) if f.endswith(".before-restructure")]
                if not снап:
                    self.skipTest(f"{b}: нет слепка до сборки")
                книга = os.path.join(d, снап[0][:-len(".before-restructure")])
                shutil.copy(os.path.join(d, снап[0]), книга)
                до = H.counts(H.read(книга))
                _, лог = H.quiet(S.restructure, d)
                после = H.counts(H.read(книга))
                self.проверить(b, до, после,
                               счётчики(лог).get("склеено переносов", 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
