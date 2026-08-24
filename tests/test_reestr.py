# -*- coding: utf-8 -*-
"""Реестр «правка этапа -> проверка, которая её держит».

Таблица в отчёте стареет молча: правку переименовали — и проверка, которая её
«держит», держит пустоту.  Поэтому таблица лежит здесь и сверяется машиной: у
каждой правки записан ЯКОРЬ (имя функции, постоянная или строка в исходнике)
и дерево, где эта правка живёт.  Нет якоря — либо правка не наложена, либо
переименована, и строка реестра стала выдумкой.

Строки с проверкой «—» — это НЕПОКРЫТОЕ.  Они печатаются списком и есть
список работ, а не украшение.
"""
import ast, collections, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

W = os.path.expanduser("~/booksmith-work")
# Реестр проверяет ТО дерево, которое сейчас под проверкой (`BOOKSMITH_SRC`),
# а не отдельно составленное: после применения правок в репозиторий второго
# дерева не существует, и якоря надо искать там, где живёт код.
СОСТАВ = H.SRC

# (этап, правка, дерево, файл, якорь, проверка)
РЕЕСТР = [
 # ---- Э1 -----------------------------------------------------------------
 ("Э1", "в READ добавлено -raw_tex", СОСТАВ, "convert.py", "-raw_tex",
  "e1/test_convert.py П21-24; e6/test_convert_stand.py"),
 ("Э1", "в READ добавлено -superscript-subscript", СОСТАВ, "convert.py",
  "-superscript-subscript", "e1/test_convert.py П25-П26"),
 ("Э1", "парная обёртка вместо strip(' {}')", СОСТАВ, "convert.py", "_unbrace",
  "e1/test_convert.py П1-П3"),
 ("Э1", "починка <mark> с чётностью слэшей", СОСТАВ, "convert.py", "_fix_marks",
  "e1/test_convert.py П5-П12; e1/test_marks.py (25)"),
 ("Э1", "санитайзер незакрытой \\cmd{", СОСТАВ, "convert.py", "_close_commands",
  "e1/test_convert.py П13-П16"),
 ("Э1", "epub сверяется по уникальным файлам", СОСТАВ, "convert.py",
  "файлов картинок", "e1/test_convert.py П32-П33"),
 ("Э1", "_report печатает величину провала", СОСТАВ, "convert.py", "_gap",
  "e1/test_convert.py П19-П20"),
 ("Э1", "код возврата не коротит после первой беды", СОСТАВ, "convert.py",
  "if not _report(", "e1/test_convert.py П30-П31; e6/test_convert_stand.py"),
 # ---- Э2 -----------------------------------------------------------------
 ("Э2", "постраничный выбор основы", f"{W}/e2/src", "merge.py", "choose_base",
  "e2/check.py 1-7 (× 6 книг)"),
 ("Э2", "разметка книги по страницам", f"{W}/e2/src", "merge.py", "page_spans",
  "e2/check.py 1"),
 ("Э2", "охрана слов при выборе", f"{W}/e2/src", "merge.py", "KEEP_WORDS",
  "e2/check.py 3-4"),
 ("Э2", "ссылки на невыгруженные вырезки", f"{W}/e2/src", "merge.py",
  "drop_lost_scans", "e2/check.py 6"),
 ("Э2", "детектор зацикливания как критерий выбора", f"{W}/e2/src", "merge.py",
  "def looping", "e2/check.py 4 (косвенно)"),
 ("Э2", "⚠ основы не теряются при подмене страницы", f"{W}/e2/src", "merge.py",
  "choose_base", "—"),
 ("Э2", "половины таблицы не приходят из разных проходов", f"{W}/e2/src",
  "merge.py", "page_spans", "—"),
 # ---- Э3 -----------------------------------------------------------------
 ("Э3", "нормализация ключа ячейки с жёсткой границей", СОСТАВ, "merge.py",
  "def cell_key", "e6/test_pometki.py ГраницаНормализации"),
 ("Э3", "пустая ячейка входит в знаменатель", СОСТАВ, "merge.py", "empty",
  "e6/test_pometki.py Знаменатель"),
 ("Э3", "сличение по множеству, а не по кратности", СОСТАВ, "merge.py",
  "k in keys", "e6/test_pometki.py test_кратность"),
 ("Э3", "варианты свидетелей кладутся в title", СОСТАВ, "merge.py",
  "_witness_values", "e6/test_pometki.py test_расхождение_названо"),
 ("Э3", "ячейка помнит, что уже помечена", СОСТАВ, "merge.py",
  'endswith("≠")', "e6/test_idempotent.py test_mark_cells"),
 ("Э3", "детектор зацикливания", СОСТАВ, "merge.py", "def looping_pages",
  "e3/verify_loop.py (замер, не приёмка) — «—»"),
 ("Э3", "слепые абзацы: счёт не растёт от числа свидетелей", СОСТАВ,
  "merge.py", "aligned", "—"),
 # ---- Э4 -----------------------------------------------------------------
 ("Э4", "подписи не зашиты на Fig.", f"{W}/e4/src", "structure.py",
  "FIGURE_WORDS", "—"),
 ("Э4", "покрытие не превышает 100%", f"{W}/e4/src", "structure.py",
  "def caption_kind", "—"),
 ("Э4", "возврат колонцифр из json", f"{W}/e4/src", "structure.py",
  "колонцифр возвращено", "e6/test_ne_ubylo.py (не убыло), e6/test_idempotent.py"),
 ("Э4", "возврат номеров формул", f"{W}/e4/src", "structure.py",
  "номер формулы", "e6/test_ne_ubylo.py (не убыло)"),
 ("Э4", "проверка целостности скана по колонцифрам", f"{W}/e4/src",
  "structure.py", "ДЕФЕКТ СКАНА", "—"),
 ("Э4", "«Таблица N» не становится заголовком", f"{W}/e4/src", "structure.py",
  "TABLE_WORDS", "—"),
 ("Э4", "отчёт идемпотентен", f"{W}/e4/src", "structure.py",
  "проходов сборки структуры",
  "e6/test_idempotent.py test_restructure_отчёт — КРАСНЫЙ"),
 # ---- Э5 -----------------------------------------------------------------
 ("Э5", "текстовый слой как второй свидетель", None, None, None,
  "— (продукта этапа нет на диске)"),
 # ---- Э7 -----------------------------------------------------------------
 ("Э7", "реестр ручек и полнота слепка", f"{W}/e7/src", "cli.py", "cmd_replay",
  "e7/test_knobs_registry.py, e7/test_replay_check.py"),
 ("Э7", "коды этапов в run.json", f"{W}/e7/src", "layout.py", "def record_stage",
  "e7/test_stage_rc.py"),
 ("Э7", "_done_pages считает только страницы с .md", f"{W}/e7/src",
  "jobs/paddleocr/entrypoint.py", "_done_pages", "e7/test_done_pages.py"),
 ("Э7", "pull_exclude только imgs/", f"{W}/e7/src", "cli.py", "pull_exclude",
  "e7/tools/weigh_stand.py (замер) — «—»"),
 ("Э7", "books calibrate", f"{W}/e7/src", "cli.py", "cmd_calibrate", "—"),
 ("Э7", "обрезка улик снята", f"{W}/e7/src", "jobs/paddleocr/entrypoint.py",
  "logprob", "—"),
 # ---- Э6 (свои) ----------------------------------------------------------
 ("Э6", "имя книги: байты, том, служебные имена", СОСТАВ, "layout.py",
  "NAME_BYTES", "e6/test_safe_name.py (9)"),
 ("Э6", "перенос под абзацной пометкой", СОСТАВ, "structure.py", "PROSE_TAIL",
  "e6/test_perenos.py (10)"),
 ("Э6", "tidy даёт ту же книгу", СОСТАВ, "cli.py", "def cmd_tidy",
  "e6/test_tidy.py (4)"),
]


class ОдноИмяОдноТело(unittest.TestCase):
    """Правка, наложенная поверх правки, может ТИХО переопределить функцию.

    Замер: цепочка Э2 -> Э7 -> Э3 на `merge.py` ложится `patch`ем (падает один
    ханк — шапка модуля), а на выходе `looping` определена ДВАЖДЫ: Э3 на
    строке 489, Э2 на 594, и побеждает вторая.  У них разные пороги (Э3 —
    1000 знаков повтора; Э2 — доля 30-грамм 0.55 и сжимаемость 0.085), то
    есть `choose_base` из Э2 берёт свой детектор, а пометки Э3 — свой, хотя
    план требовал написать его ОДИН раз.  `patch` этого не видит, дерево
    разбора видит.
    """

    def test_ни_одна_функция_не_определена_дважды(self):
        for файл in ("merge.py", "structure.py", "convert.py", "layout.py",
                     "cli.py"):
            p = os.path.join(СОСТАВ, "booksmith", файл)
            if not os.path.exists(p):
                continue
            with self.subTest(файл=файл):
                t = ast.parse(H.read(p))
                c = collections.Counter(
                    n.name for n in t.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)))
                дубли = {k: v for k, v in c.items() if v > 1}
                self.assertFalse(дубли, f"{файл}: {дубли}")

    def test_постоянные_не_объявлены_дважды(self):
        for файл in ("merge.py", "structure.py"):
            p = os.path.join(СОСТАВ, "booksmith", файл)
            if not os.path.exists(p):
                continue
            with self.subTest(файл=файл):
                t = ast.parse(H.read(p))
                имена = [x.id for n in t.body if isinstance(n, ast.Assign)
                         for x in n.targets if isinstance(x, ast.Name)
                         and x.id.isupper() and len(x.id) > 2]
                дубли = {k: v for k, v in collections.Counter(имена).items()
                         if v > 1}
                self.assertFalse(дубли, f"{файл}: {дубли}")


class Реестр(unittest.TestCase):

    def test_у_каждой_правки_есть_якорь(self):
        нет = []
        for э, правка, дерево, файл, якорь, тест in РЕЕСТР:
            if дерево is None:
                continue
            p = os.path.join(дерево, "booksmith", файл)
            if not os.path.exists(p):
                нет.append(f"{э} «{правка}»: нет файла {p}")
                continue
            if якорь not in H.read(p):
                нет.append(f"{э} «{правка}»: якоря {якорь!r} нет в {файл} "
                           f"({os.path.relpath(дерево, W)})")
        self.assertFalse(нет, "\n".join(нет))

    def test_непокрытое_названо(self):
        """Не падает: печатает список работ."""
        голые = [(э, п) for э, п, *_ , т in РЕЕСТР if т.strip().startswith("—")
                 or "«—»" in т]
        print(f"\nправок без держащей проверки: {len(голые)} из {len(РЕЕСТР)}")
        for э, п in голые:
            print(f"  {э}  {п}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
