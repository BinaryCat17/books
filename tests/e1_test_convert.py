# -*- coding: utf-8 -*-
"""Приёмка Э1. Запуск: python3 test_convert.py [каталог-с-booksmith]

Каждая проверка написана под мутацию: см. mutants.py — там перечислено, какая
именно порча кода её роняет.  Проверка, не падающая ни на одной мутации, — фон.
"""
import os, re, shutil, subprocess, sys, tempfile, zipfile

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/booksmith-work/e1/src2")
sys.path.insert(0, SRC)
import booksmith.convert as C

ok = bad = 0
def t(name, cond, note=""):
    global ok, bad
    if cond: ok += 1
    else:
        bad += 1
        print(f"ПРОВАЛ {name}{(': ' + note) if note else ''}")

M = '<mark title="модель не уверена">'

# ---- чистые функции ------------------------------------------------------
t("П1 парная обёртка снимается", C._unbrace("{abc}") == "abc")
t("П2 команда не калечится", C._unbrace("\\mathrm{Fe}") == "\\mathrm{Fe}",
  C._unbrace("\\mathrm{Fe}"))
t("П3 непарные скобки не снимаются", C._unbrace("{a}+{b}") == "{a}+{b}")
t("П4 массив собирается без огрызков",
  "\\mathrm{Fe}" in C._plain_math("\\begin{array}{cc}\\mathrm{Fe} & 2\\end{array}")
  or C._plain_math("\\begin{array}{cc}\\mathrm{Fe} & 2\\end{array}") == "Fe  2",
  C._plain_math("\\begin{array}{cc}\\mathrm{Fe} & 2\\end{array}"))

t("П5 слэш снят с закрывающего тега",
  C._fix_marks(f"a{M} $\\</mark>Phi")[0] == f"a{M} $</mark>\\Phi")
t("П6 ЧЁТНАЯ серия слэшей не тронута",
  C._fix_marks(f"a{M}b\\\\</mark>c")[0] == f"a{M}b\\\\</mark>c")
t("П7 нечётная серия из трёх — снят один",
  C._fix_marks(f"{M}b\\\\\\</mark>c")[0] == f"{M}b\\\\</mark>\\c")
t("П8 слэш снят с открывающего тега",
  C._fix_marks(f"$t_{{\\{M}lambda</mark>}}$")[0] == f"$t_{{{M}\\lambda</mark>}}$")
t("П9 спан через абзац перевыставлен",
  C._fix_marks(f"{M}а\n\nб</mark>")[0] == f"{M}а</mark>\n\n{M}б</mark>")
t("П10 здоровая разметка неизменна",
  C._fix_marks(f"а {M}б</mark> в")[0] == f"а {M}б</mark> в")
t("П11 починка идемпотентна",
  C._fix_marks(C._fix_marks(f"{M} $\\</mark>Phi\n\n{M}а\n\nб</mark>")[0])[0]
  == C._fix_marks(f"{M} $\\</mark>Phi\n\n{M}а\n\nб</mark>")[0])
def _balanced(md):
    for blk in re.split(r"\n[ \t]*\n", md):
        d = 0
        for m in C.MARK_TAG.finditer(blk):
            d += -1 if m.group(0).startswith("</") else 1
            if d < 0 or d > 1:
                return False
        if d:
            return False
    return True
t("П12 после починки пометки парны в каждом абзаце",
  _balanced(C._fix_marks(f"{M}а\n\nб</mark>\n\nв\\</mark>\n\n{M}г")[0]),
  C._fix_marks(f"{M}а\n\nб</mark>\n\nв\\</mark>\n\n{M}г")[0])

t("П13 висячая \\cmd{ закрывается в абзаце",
  C._close_commands("\\mathrm{Fe и дальше\n\nдругой") ==
  ("\\mathrm{Fe и дальше}\n\nдругой", 1))
t("П14 закрытая не трогается",
  C._close_commands("\\mathrm{Fe} тут") == ("\\mathrm{Fe} тут", 0))
t("П15 одинокая { без команды не трогается",
  C._close_commands("пункт {3") == ("пункт {3", 0))
t("П16 закрытая скобка даёт читаемый текст",
  C._plain_math(C._close_commands("$\\mathrm{Fe}$")[0]) == "Fe")

# ---- отчёт, провал, код возврата ----------------------------------------
src = {"таблиц": 10, "картинок": 5}
t("П17 полный вывод даёт True",
  C._report("x", src, {"таблиц": 10, "картинок": 5}) is True)
t("П18 потеря даёт False",
  C._report("x", src, {"таблиц": 4, "картинок": 5}) is False)

md = "".join(f"<table><tr><td>строка номер {i} таблицы</td></tr></table>\n\n"
             for i in range(10))
cut = "".join(f"<table><tr><td>строка номер {i} таблицы</td></tr></table>\n\n"
              for i in (0, 1, 9))
n, line, head = C._gap(md, cut)
t("П19 величина провала названа числом", n == 7, f"пропало {n}")
t("П20 названа строка первой пропавшей", line == 5, f"строка {line}")

# ---- сборка через pandoc -------------------------------------------------
FIX = """# Книга

Абзац с незакрытой командой \\mathrm{СЮДА и дальше без закрытия.

Второй абзац, который обязан доехать.

<div style="text-align: center;"><img src="i.png" alt="к" /></div>

<table><tr><td>ячейка первой таблицы</td></tr></table>

Команда \\mathbb{ВИДНО} внутри абзаца, скобки парны.

Надстрочник 2^10^ и подстрочник H~2~O.

Третий абзац} после скобки.
"""
def build(fmt="html5"):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "b.md"), "w", encoding="utf-8").write(
        C._prepare(FIX)[0])
    open(os.path.join(d, "i.png"), "wb").write(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000"
                      "001f15c4890000000a49444154789c6300010000050001"
                      "0d0a2db40000000049454e44ae426082"))
    r = subprocess.run(["pandoc", "b.md", "-f", C.READ, "-t", fmt,
                        "--resource-path=."], cwd=d, capture_output=True, text=True)
    return r.stdout, d

out, d = build()
t("П21 второй абзац доехал", "Второй абзац" in out, out[:200])
t("П22 таблица доехала", "<table" in out.lower())
t("П23 картинка доехала", "<img" in out.lower())
t("П24 третий абзац доехал", "Третий абзац" in out)
t("П25 ложного <sup> нет", "<sup" not in out, out[out.find("Надстрочник"):][:120])
t("П26 ложного <sub> нет", "<sub" not in out)
t("П27 \\mathrm обезврежен и виден текстом",
  "СЮДА" in out, out[:300])
t("П29 парная \\cmd{} не съедает содержимое",
  "ВИДНО" in out, out[out.find("Команда"):][:160])
shutil.rmtree(d, ignore_errors=True)

# ---- сверка не молчит после первой беды ----------------------------------
import io, contextlib, json
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "passes", "1"))
open(os.path.join(d, "run.json"), "w").write(json.dumps({"stem": "b"}))
open(os.path.join(d, "b.md"), "w", encoding="utf-8").write(FIX)
real = C._pandoc
def broken(args, cwd=None):
    if "epub3" in args:
        raise RuntimeError("нарочно")
    return real(args, cwd=cwd)
C._pandoc = broken
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc_got = C.convert(d, formats=("html", "epub", "fb2"))
C._pandoc = real
log = buf.getvalue()
t("П30 после провала epub отчёт по html всё равно печатается",
  "b.html" in log, log)
t("П31 провал одного формата даёт ненулевой код", rc_got == 1, str(rc_got))
shutil.rmtree(d, ignore_errors=True)

# ---- epub сверяется по файлам, а не по тегам ------------------------------
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "passes", "1"))
open(os.path.join(d, "run.json"), "w").write(json.dumps({"stem": "b"}))
open(os.path.join(d, "b.md"), "w", encoding="utf-8").write(
    'Раз <img src="i.png" alt="к" />\n\nДва <img src="i.png" alt="к" />\n')
open(os.path.join(d, "i.png"), "wb").write(
    bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000"
                  "001f15c4890000000a49444154789c630001000005000101"
                  "0d0a2db40000000049454e44ae426082"))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc_got = C.convert(d, formats=("epub",))
log = buf.getvalue()
t("П32 два тега на один файл — не повод кричать", rc_got == 0, log)
t("П33 в отчёте назван счёт файлов", "файлов картинок 1" in log, log)
shutil.rmtree(d, ignore_errors=True)

# ---- память ---------------------------------------------------------------
big = "\n\n".join(f'<div style="text-align: center;">строка {i}</div>'
                  for i in range(4000))
d = tempfile.mkdtemp()
open(os.path.join(d, "b.md"), "w", encoding="utf-8").write(big)
r = subprocess.run(["/usr/bin/time", "-f", "%M", "pandoc", "b.md", "-f", C.READ,
                    "-t", "html5", "-o", os.devnull], cwd=d,
                   capture_output=True, text=True)
peak = int(r.stderr.strip().split()[-1]) if r.returncode == 0 else 10 ** 9
t("П28 тысячи div не раздувают память", peak < 400_000, f"пик {peak} КБ")
shutil.rmtree(d, ignore_errors=True)

print(f"\nпройдено {ok}, провалено {bad}")
sys.exit(1 if bad else 0)
