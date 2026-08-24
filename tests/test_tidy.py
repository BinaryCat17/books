# -*- coding: utf-8 -*-
"""`books tidy` обязан дать байт в байт ту же книгу, что и прямая сборка.

Перевод старой раскладки в нынешнюю — необратимое действие над каталогом,
который стоил денег: он двигает проходы, поднимает форматы наверх и удаляет
копии.  Первая редакция шага сносила `book/` целиком и молча уносила epub,
fb2 и `перевод.md`.  Проверка сравнивает не «шаг отработал», а сам текст:
книга после `tidy` и книга после `merge` + `restructure` из тех же проходов
должны совпасть побайтово.

Старая раскладка строится из стенда: `<имя>-pass1..3` соседями плюс копия
первого прохода внутри `<имя>`, как оно и было.
"""
import argparse, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

L = H.mod("layout")
M = H.mod("merge")
S = H.mod("structure")
CLI = H.mod("cli")


def старая_раскладка(stand, корень, имя):
    """Разложить стенд так, как лежали разборы до нынешней раскладки."""
    src = os.path.join(H.STAND, stand)
    for p in sorted(os.listdir(os.path.join(src, "passes"))):
        shutil.copytree(os.path.join(src, "passes", p),
                        os.path.join(корень, f"{имя}-pass{p}"))
    сам = os.path.join(корень, имя)
    shutil.copytree(os.path.join(корень, f"{имя}-pass1"), сам)
    # `run.json` старого образца: ни stem, ни source в нём не было.
    open(os.path.join(сам, "run.json"), "w", encoding="utf-8").write(
        '{"pages": 12, "model": "PaddleOCR-VL"}')
    return сам


def новая_раскладка(stand, корень, имя):
    dst = os.path.join(корень, имя)
    shutil.copytree(os.path.join(H.STAND, stand), dst)
    return dst


class ПереводРаскладки(unittest.TestCase):

    def прогнать(self, stand):
        имя = "Книга. Том 1"
        корень = tempfile.mkdtemp(prefix="e6-tidy-")
        try:
            a = os.path.join(корень, "a")
            b = os.path.join(корень, "b")
            os.makedirs(a)
            os.makedirs(b)
            старый = старая_раскладка(stand, a, "kniga")
            H.quiet(CLI.cmd_tidy, argparse.Namespace(
                outdir=старый, pdf=имя + ".pdf", force=False))
            прямой = новая_раскладка(stand, b, "kniga")
            open(os.path.join(прямой, "run.json"), "w", encoding="utf-8").write(
                '{"stem": "%s", "source": "%s.pdf", "passes": 3}'
                % (L.clean_stem(имя + ".pdf"), имя))
            H.quiet(M.assemble, прямой)
            H.quiet(S.restructure, прямой)
            return старый, прямой
        finally:
            self.addCleanup(shutil.rmtree, корень, True)

    def test_книга_байт_в_байт(self):
        for stand in H.STANDS:
            with self.subTest(книга=stand):
                после_tidy, прямая = self.прогнать(stand)
                pa, pb = L.Paths(после_tidy), L.Paths(прямая)
                self.assertEqual(os.path.basename(pa.book),
                                 os.path.basename(pb.book),
                                 "книга названа по-разному")
                self.assertEqual(H.read(pa.book), H.read(pb.book),
                                 "tidy дал другой текст, чем прямая сборка")
                self.assertEqual(H.read(pa.toc), H.read(pb.toc))

    def test_имя_книги_из_pdf_а_не_из_каталога(self):
        """Каталог оператор называет наспех; книга должна называться книгой."""
        после_tidy, _ = self.прогнать("ogneupory")
        p = L.Paths(после_tidy)
        self.assertEqual(p.stem, "Книга._Том_1", p.stem)
        self.assertTrue(os.path.exists(p.book))

    def test_чужие_файлы_не_погибли(self):
        """Удаляем только своё: заметки человека и собранные форматы — не наши."""
        корень = tempfile.mkdtemp(prefix="e6-tidy-")
        self.addCleanup(shutil.rmtree, корень, True)
        старый = старая_раскладка("ogneupory", корень, "kniga")
        open(os.path.join(старый, "book", "book.epub"), "w").write("epub")
        open(os.path.join(старый, "book", "ЗАМЕТКИ.md"), "w").write("моё")
        open(os.path.join(старый, "перевод.md"), "w").write("перевод")
        H.quiet(CLI.cmd_tidy, argparse.Namespace(
            outdir=старый, pdf="Книга.pdf", force=False))
        живы = os.listdir(старый)
        self.assertIn("перевод.md", живы, живы)
        self.assertTrue(any(x.endswith(".epub") for x in живы), живы)
        self.assertIn("ЗАМЕТКИ.md", живы, живы)

    def test_повтор_безопасен(self):
        """Второй `tidy` по уже переведённому каталогу не смеет ничего трогать."""
        после_tidy, _ = self.прогнать("ogneupory")
        p = L.Paths(после_tidy)
        было = {f: H.digest(os.path.join(после_tidy, f))
                for f in os.listdir(после_tidy)
                if os.path.isfile(os.path.join(после_tidy, f))}
        rc, _ = H.quiet(CLI.cmd_tidy, argparse.Namespace(
            outdir=после_tidy, pdf=None, force=False))
        self.assertEqual(rc, 0)
        стало = {f: H.digest(os.path.join(после_tidy, f))
                 for f in os.listdir(после_tidy)
                 if os.path.isfile(os.path.join(после_tidy, f))}
        self.assertEqual(было, стало)


if __name__ == "__main__":
    unittest.main(verbosity=2)
