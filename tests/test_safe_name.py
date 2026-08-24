# -*- coding: utf-8 -*-
"""Имя книги: том не откусывать, служебное имя обезвредить, резать по БАЙТАМ.

Мутации, на которых падает каждая проверка, перечислены в `mutants.py`
(раздел `layout.py`).  Проверка, не падающая ни на одной, — фон.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

L = H.mod("layout")
LIMIT = L.NAME_BYTES - len(L.LONGEST_SUFFIX.encode())


class ИмяКниги(unittest.TestCase):

    def test_том_не_откушен(self):
        """`Фейнмановские_лекции_по_физике._1` — законное имя, `._1` не расширение."""
        n = "Фейнмановские_лекции_по_физике._1"
        self.assertEqual(L.safe_name(n), n)

    def test_clean_stem_снимает_расширение_а_safe_name_нет(self):
        """Две разные работы; слив их в одну, мы и теряли том."""
        self.assertEqual(L.clean_stem("Фейнман. 1.pdf"), "Фейнман._1")
        self.assertEqual(L.safe_name("Фейнман._1"), "Фейнман._1")

    def test_служебные_имена_обезврежены(self):
        """`report.pdf` давал `report.md` — отчёт писался поверх книги."""
        for имя in ("report", "Report", "REPORT", "run", "RuN"):
            with self.subTest(имя=имя):
                got = L.safe_name(имя)
                self.assertNotEqual(got.casefold(), имя.casefold())
                self.assertNotIn(got.casefold(), L.RESERVED)
        # А имя книги, лишь начинающееся с этих букв, трогать нельзя.
        self.assertEqual(L.safe_name("reportazh"), "reportazh")

    def test_режется_по_байтам_а_не_по_знакам(self):
        """Кириллический заголовок в 120 знаков — это 240 байт."""
        for знак in ("Я", "字", "😀"):
            with self.subTest(знак=знак):
                s = L.safe_name(знак * 300)
                b = len((s + L.LONGEST_SUFFIX).encode())
                self.assertLessEqual(b, L.NAME_BYTES,
                                     f"{знак*3}…: с хвостом {b} байт")
                self.assertLessEqual(len(s.encode()), LIMIT)

    def test_обрезок_остаётся_годным_utf8(self):
        """Резать по байтам нельзя посреди знака: имя должно открываться."""
        s = L.safe_name("Я" * 300)
        s.encode("utf-8").decode("utf-8")          # не падает
        self.assertNotIn("�", s)

    def test_короткое_имя_не_трогается(self):
        for имя in ("chugun", "Технология_огнеупоров", "a.b.c"):
            self.assertEqual(L.safe_name(имя), имя)

    def test_путь_и_управляющие_знаки_обезврежены(self):
        for имя in ("../../etc/passwd", "a/b", "a\\b", "a\x00b", "a\nb"):
            with self.subTest(имя=имя):
                got = L.safe_name(имя)
                self.assertNotIn("/", got)
                self.assertNotIn("\\", got)
                self.assertFalse(any(ord(c) < 32 for c in got))

    def test_пустое_имя_даёт_книгу(self):
        for имя in ("", "   ", ".__.", "///"):
            self.assertTrue(L.safe_name(имя))

    def test_идемпотентно(self):
        """`stem()` прогоняет через safe_name прочитанное — второй раз не должен менять."""
        for имя in ("report", "Я" * 300, "Фейнмановские_лекции_по_физике._1",
                    "a/b", ""):
            with self.subTest(имя=имя):
                once = L.safe_name(имя)
                self.assertEqual(L.safe_name(once), once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
