# -*- coding: utf-8 -*-
"""Пометка свода не должна отменять склейку переноса — и не должна пропадать.

Настоящий случай (Фейнман, строка 470): «Диаметр атома примерно 10⁻⁸см, а
яд-» + «ра».  Свод дописывает `≠` в КОНЕЦ абзаца, дефис перестаёт быть
последним знаком, признак переноса не срабатывает — и слово «ядра» остаётся
разорванным пополам в читаемом тексте.  Замер: склеек 48 без пометок, 47 с
ними; заметили случайно.

Образец — цитата, а не выдумка: `fixtures/perenos-pod-pometkoy.md`,
провенанс рядом.
"""
import os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

S = H.mod("structure")
ХВОСТ = re.compile(r"(?:\s*≠)+$")


def склеить(t):
    return H.need(S, "join_hyphens")(t)


class ПереносПодПометкой(unittest.TestCase):

    def setUp(self):
        self.цитата = open(os.path.join(H.FIX, "perenos-pod-pometkoy.md"),
                           encoding="utf-8").read()

    # ---- рукотворные границы (быстро, точно) ------------------------------
    def test_склейка_под_пометкой_происходит(self):
        было = "а яд- ≠\n\nра — что-то около 10⁻¹³ см.\n"
        стало, n = склеить(было)
        self.assertEqual(n, 1, f"склеек {n}, ждали 1: {стало!r}")
        self.assertIn("ядра", стало, стало)

    def test_пометка_после_склейки_на_месте(self):
        стало, _ = склеить("а яд- ≠\n\nра — что-то около 10⁻¹³ см.\n")
        self.assertEqual(стало.count("≠"), 1, стало)
        строка = [l for l in стало.split("\n") if "ядра" in l][0]
        self.assertTrue(ХВОСТ.search(строка),
                        f"пометка съехала с конца абзаца: {строка!r}")

    def test_пометка_не_задваивается(self):
        """Второй прогон не должен дописать `≠` ещё раз."""
        раз, _ = склеить("а яд- ≠\n\nра дальше.\n")
        два, n2 = склеить(раз)
        self.assertEqual(раз, два)
        self.assertEqual(n2, 0)

    def test_несколько_пометок_переживают_склейку(self):
        стало, n = склеить("а яд- ≠ ≠\n\nра дальше.\n")
        self.assertEqual(n, 1)
        self.assertIn("ядра", стало)
        self.assertGreaterEqual(стало.count("≠"), 1)

    def test_настоящий_дефис_под_пометкой_не_склеивается(self):
        """Следующая строка с прописной — дефис настоящий."""
        было = "речь о Two- ≠\n\nPhase системе.\n"
        стало, n = склеить(было)
        self.assertEqual(n, 0, стало)
        self.assertIn("Two-", стало)

    # ---- цитата из книги --------------------------------------------------
    def test_на_цитате_из_книги_слово_собирается(self):
        стало, n = склеить(self.цитата)
        self.assertGreaterEqual(n, 1, "на настоящей цитате не склеилось ничего")
        self.assertIn("ядра", стало,
                      "слово «ядра» осталось разорванным на настоящем тексте")
        self.assertNotIn("яд- ≠", стало)

    def test_на_цитате_пометки_не_убыло(self):
        было = self.цитата.count("≠")
        стало, _ = склеить(self.цитата)
        self.assertGreaterEqual(стало.count("≠"), было,
                                f"пометок было {было}, стало {стало.count('≠')}")

    def test_склейка_идёт_до_неподвижности(self):
        """Приклеенный кусок сам может кончаться переносом."""
        было = "пере- ≠\n\nнос- \n\nный текст\n"
        стало, n = склеить(было)
        _, ещё = склеить(стало)
        self.assertEqual(ещё, 0, f"второй проход нашёл ещё {ещё}: {стало!r}")

    def test_настоящие_дефисы_из_книги_целы(self):
        путь = os.path.join(H.FIX, "defis-nastoyashchiy.md")
        if not os.path.exists(путь):
            self.skipTest("образца нет")
        цитата = open(путь, encoding="utf-8").read()
        стало, n = склеить(цитата)
        self.assertEqual(n, 0, f"склеено {n} настоящих дефисов: {стало[:300]!r}")

    # ---- медленный слой: вся книга ----------------------------------------
    @unittest.skipUnless(H.SLOW, "медленно: настоящая книга (E6_SLOW=1)")
    def test_на_всей_книге_склеек_столько_же_с_пометками_и_без(self):
        M = H.mod("merge")
        d = os.path.join(H.BOOKS, "feynman-1", "passes")
        b = open(os.path.join(d, "1", "book", "book.md"), encoding="utf-8").read()
        w = [open(os.path.join(d, str(k), "book", "book.md"),
                  encoding="utf-8").read() for k in (2, 3)]
        чистый, _ = склеить(S._protect(b)[0])
        помеченный, _pr, _bl = M.mark_prose(b, w)
        _, с_пометками = склеить(S._protect(помеченный)[0])
        _, без = склеить(S._protect(b)[0])
        self.assertEqual(с_пометками, без,
                         f"без пометок {без}, с пометками {с_пометками}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
