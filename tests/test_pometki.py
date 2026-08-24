# -*- coding: utf-8 -*-
"""Пометки: где граница нормализации и что входит в знаменатель.

Пометка `≠` — единственное, что книга сообщает о своей надёжности, и до сих
пор она мерилась без единиц.  Здесь закреплены границы, которые уже
переступали:

  * нормализация ячейки не смеет слить `1,5` с `15` — снос всей пунктуации
    давал 753 группы и 2385 ложных слияний; в одних огнеупорах таких пар 57
    (`fixtures/desyatichnaya-zapyataya.md`, цитата из книги);
  * пустая ячейка обязана входить в ЗНАМЕНАТЕЛЬ — иначе доля помеченных
    считается по неполной книге: 3077 ячеек (8.6%) в 312 таблицах из 943;
  * `≠` не должна появляться от кратности: одна и та же ячейка, встреченная
    у основы дважды, а у свидетеля один раз, — не расхождение значения.
"""
import os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

M = H.mod("merge")


def ячейки(md):
    return [x for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", md, re.I | re.S)]


class ГраницаНормализации(unittest.TestCase):

    def test_запятая_не_сливается_с_её_отсутствием(self):
        """`1,5` и `15` — разные числа, и разными обязаны остаться."""
        цитата = H.read(os.path.join(H.FIX, "desyatichnaya-zapyataya.md"))
        ключ = getattr(M, "cell_key", M.plain)
        пары = [(a, b) for a, b in zip(*[iter(ячейки(цитата))] * 2)]
        self.assertTrue(пары, "в образце нет пар")
        for a, b in пары:
            with self.subTest(пара=(a, b)):
                self.assertNotEqual(ключ(a), ключ(b),
                                    f"«{a}» и «{b}» слиты в один ключ")

    def test_одно_число_разными_написаниями_считается_одним(self):
        for a, b in ((".001", "0.001"), ("0,5", "0.5"), (".0005", "0.0005")):
            with self.subTest(пара=(a, b)):
                self.assertTrue(M._same_number(a, b), f"{a} != {b}")

    def test_разные_числа_остаются_разными(self):
        for a, b in ((".001", ".0001"), ("1", "10"), ("1,5", "15")):
            with self.subTest(пара=(a, b)):
                self.assertFalse(M._same_number(a, b), f"{a} == {b}")


class Знаменатель(unittest.TestCase):

    def test_пустая_ячейка_входит_в_знаменатель(self):
        """На нынешнем коде красный: `if not v: return` стоит ДО `total += 1`.

        Пустая ячейка не метится и не считается, и доля помеченных выходит от
        неполной книги — 3077 ячеек (8.6%) в 312 таблицах из 943.
        """
        цитата = H.read(os.path.join(H.FIX, "pustye-yacheyki.md"))
        всего_в_разметке = len(re.findall(r"<t[dh]\b", цитата, re.I))
        got = M.mark_cells(цитата, [цитата])
        total = got[2]
        self.assertEqual(
            total, всего_в_разметке,
            f"в разметке {всего_в_разметке} ячеек, в знаменателе {total} — "
            f"{всего_в_разметке - total} не сосчитаны")

    def test_кратность_не_даёт_пометки(self):
        """Ячейка, встреченная у основы дважды, а у свидетеля раз, — не расхождение.

        Артефакт кратности: 1490 пометок из 7101 (21%).
        """
        основа = "<table><tr><td>0,25</td><td>0,25</td></tr></table>"
        свидетель = "<table><tr><td>0,25</td></tr></table>"
        out = M.mark_cells(основа, [свидетель])[0]
        self.assertEqual(out.count("≠"), 0,
                         f"пометка от кратности: {out}")

    def test_согласный_свидетель_не_даёт_пометок(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                t = H.read(os.path.join(H.STAND, b, "passes", "1", "book", "book.md"))
                out, n = M.mark_cells(t, [t])[:2]
                self.assertEqual(n, 0, f"сам с собой разошёлся в {n} ячейках")


class ПрозаическаяПометка(unittest.TestCase):

    def test_внутрь_формулы_не_заходим(self):
        """Пометка внутри `$…$` ломает саму формулу."""
        база = "Величина $t_{\\lambda} = 0.0049$ важна.\n"
        свид = "Величина $t_{\\lambda} = 0.0051$ важна.\n"
        out = M.mark_prose(база, [свид])[0]
        self.assertNotIn("<mark", out.split("$")[1] if out.count("$") > 1 else "",
                         out)

    def test_расхождение_числа_названо_поимённо(self):
        база = "Допуск равен 0.001 дюйма и не более.\n"
        свид = "Допуск равен 0.007 дюйма и не более.\n"
        out, n, _ = M.mark_prose(база, [свид])
        self.assertGreaterEqual(n, 1, out)
        self.assertIn("0.007", out, "вариант свидетеля не положен в подпись")

    def test_согласные_свидетели_не_дают_пометок(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                t = H.read(os.path.join(H.STAND, b, "passes", "1", "book", "book.md"))
                _, n, _ = M.mark_prose(t, [t])
                self.assertEqual(n, 0, f"сам с собой разошёлся {n} раз")

    def test_ложный_минус_запятой_назван(self):
        """Известный ложный минус: `1,200` (англ. 1200) и `1.200` (нем. 1.2).

        Замер: столкновений 0 на 799 страницах и шести чтениях — цена
        известна и принята.  Проверка стоит здесь, чтобы поведение не
        поменялось молча в обе стороны.
        """
        self.assertTrue(M._same_number("1,200", "1.200"),
                        "поведение сменилось — пересчитайте цену по книгам")


if __name__ == "__main__":
    unittest.main(verbosity=2)
