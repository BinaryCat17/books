# -*- coding: utf-8 -*-
"""Сборка форматов на настоящем куске книги: что вышло из книги, то и доехало.

Проверки Э1 (`e1/tests/test_convert.py`) держат чистые функции и подставки в
десяток строк.  Здесь — тот же тракт на НАСТОЯЩЕМ тексте: 12 страниц книги со
своими таблицами, картинками и пометками.  Ровно этот разрыв и стоил
«Справочнику» половины: подставка из трёх абзацев не содержит незакрытой
`\\cmd{`, за которую pandoc читает вперёд через абзацы и таблицы.

PDF НЕ СОБИРАЕТСЯ: WeasyPrint держит документ в памяти целиком, на шести
книгах это стоило 10.9 ГБ и дважды роняло WSL.  pandoc зовётся ТОЛЬКО через
обёртку с жёстким потолком RSS (`e1/tools/bin/pandoc`), она ставится в PATH
здесь же.
"""
import os, re, shutil, subprocess, sys, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

ОБЁРТКА = os.path.expanduser("~/booksmith-work/e1/tools/bin")
os.environ["PATH"] = ОБЁРТКА + os.pathsep + os.environ["PATH"]
os.environ.setdefault("E1_PANDOC_CAP", "2000M")

C = H.mod("convert")
M = H.mod("merge")
S = H.mod("structure")
L = H.mod("layout")
ФОРМАТЫ = ("html", "epub", "fb2")


def _есть_pandoc():
    return shutil.which("pandoc") is not None


def _под_потолком():
    """Обёртка обязана быть первой в PATH: без неё сборка роняла машину."""
    return shutil.which("pandoc") == os.path.join(ОБЁРТКА, "pandoc")


@unittest.skipUnless(_есть_pandoc(), "нет pandoc")
class СборкаФорматов(unittest.TestCase):

    def test_обёртка_с_потолком_стоит_первой(self):
        self.assertTrue(_под_потолком(),
                        f"pandoc берётся из {shutil.which('pandoc')} — без "
                        f"потолка памяти сборку запускать нельзя")

    def собрать(self, b):
        d = H.stand_copy(b)
        self.addCleanup(shutil.rmtree, os.path.dirname(d), True)
        H.quiet(M.assemble, d)
        H.quiet(S.restructure, d)
        rc, лог = H.quiet(C.convert, d, formats=ФОРМАТЫ)
        return d, rc, лог

    def test_ничего_не_пропало_в_html(self):
        for b in H.STANDS:
            with self.subTest(книга=b):
                d, rc, лог = self.собрать(b)
                p = L.Paths(d)
                было = H.counts(H.read(p.book))
                стало = H.counts(H.read(p.book[:-3] + ".html"))
                убыло = H.less(было, стало,
                               slack=("слов", "знаков без тегов", "пометок mark"))
                self.assertFalse(убыло, f"{b}: " + "; ".join(убыло))

    def test_слова_доехали_почти_все(self):
        """Слова считаем отдельно: разметка правится, содержание — нет."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d, rc, лог = self.собрать(b)
                p = L.Paths(d)
                было = H.counts(H.read(p.book))["слов"]
                стало = H.counts(H.read(p.book[:-3] + ".html"))["слов"]
                self.assertGreaterEqual(
                    стало, было * 0.97,
                    f"{b}: слов {было} -> {стало} ({стало/было:.1%})")

    def test_fb2_не_теряет_таблиц(self):
        """Прямая конвертация давала 0 таблиц из 40 и файл выглядел целым."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d, rc, лог = self.собрать(b)
                p = L.Paths(d)
                было = H.counts(H.read(p.book))["таблиц"]
                fb2 = p.book[:-3] + ".fb2"
                self.assertTrue(os.path.exists(fb2), лог)
                стало = len(re.findall(r"<table", H.read(fb2), re.I))
                self.assertGreaterEqual(стало, было, f"{b}: {было} -> {стало}")

    def test_код_возврата_не_ноль_при_потере(self):
        """Проверка без последствий — не проверка."""
        for b in H.STANDS:
            with self.subTest(книга=b):
                d, rc, лог = self.собрать(b)
                провалы = [l for l in лог.split("\n") if " !" in l]
                if провалы:
                    self.assertNotEqual(rc, 0, "потеря названа, а код 0:\n"
                                        + "\n".join(провалы))
                else:
                    self.assertEqual(rc, 0, лог)


if __name__ == "__main__":
    unittest.main(verbosity=2)
