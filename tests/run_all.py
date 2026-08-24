# -*- coding: utf-8 -*-
"""Единый запуск всей приёмки конвейера: свои проверки и чужие.

Семь этапов оставили семь способов запуска.  Свести их в один набор — не
вопрос вкуса, а вопрос цены: `pytest` нет ни в `/home/smirn/books/.venv`, ни в
системном python3 (проверено), а ставить его нельзя — сеть закрыта.  Поэтому
общий каркас — `unittest` из стандартной поставки (стоит 0), а общий ЗАПУСК —
этот файл: у каждого набора записано, каким деревом исходников он живёт, и
код возврата один на всех.

Слои:
  быстрый  (по умолчанию)  — секунды, стенд из 12 настоящих страниц;
  медленный (E6_SLOW=1)    — минуты, шесть настоящих книг из e6/data.

PDF не собирается ни на одном пути.  pandoc зовётся только через обёртку с
жёстким потолком RSS.

Запуск:  python3 tests/run_all.py [--только Э6] [--список]
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
E6 = os.path.dirname(HERE)
W = os.path.expanduser("~/booksmith-work")
PY = "/home/smirn/books/.venv/bin/python"
if not os.path.exists(PY):
    PY = sys.executable
РЕПО = "/home/smirn/books/src"
# По умолчанию — СОСТАВЛЕННОЕ дерево (Э1+Э3+Э4 поверх репозитория): зелёный
# цвет должен означать «правки на месте», а не «правок нет».  Голый
# репозиторий гоняется явно: --дерево репо.
СВОЁ = os.path.join(E6, "src")
ОБЁРТКА = os.path.join(W, "e1", "tools", "bin")

# (этап, имя, дерево исходников, команда, чем считается)
НАБОРЫ = [
 ("Э6", "имя книги (safe_name)", None, [PY, f"{HERE}/test_safe_name.py"], "9 проверок"),
 ("Э6", "перенос под пометкой", None, [PY, f"{HERE}/test_perenos.py"], "10"),
 ("Э6", "идемпотентность", None, [PY, f"{HERE}/test_idempotent.py"], "8"),
 ("Э6", "ничего не убыло", None, [PY, f"{HERE}/test_ne_ubylo.py"], "5"),
 ("Э6", "пометки и знаменатель", None, [PY, f"{HERE}/test_pometki.py"], "10"),
 ("Э6", "перевод раскладки (tidy)", None, [PY, f"{HERE}/test_tidy.py"], "4"),
 ("Э6", "сборка форматов на стенде", None,
  [PY, f"{HERE}/test_convert_stand.py"], "5, зовёт pandoc"),
 ("Э1", "convert", f"{W}/e1/src2",
  [PY, f"{W}/e1/tests/test_convert.py", f"{W}/e1/src2"], "33"),
 ("Э1", "починка <mark>", f"{W}/e1/src2", [PY, f"{W}/e1/tests/test_marks.py"], "25"),
 ("Э1", "пометка в entrypoint", f"{W}/e1/src2",
  [PY, f"{W}/e1/tests/test_entrypoint_marks.py"], "11"),
 ("Э2", "свод: выбор основы", f"{W}/e2/src", [PY, f"{W}/e2/tools/check.py"],
  "11 × 6 книг, нужен e2/data"),
 ("Э3", "свод: пометки", f"{W}/e3/src2", [PY, f"{W}/e3/bin/verify.py"],
  "идемпотентность mark_cells, нужен e3/data"),
 ("Э7", "слепок входа и коды этапов", f"{W}/e7/src",
  ["bash", f"{W}/e7/tests/run_all.sh"], "5"),
 ("Э6", "реестр правка->тест", None, [PY, f"{HERE}/test_reestr.py"],
  "39 правок, 12 без проверки"),
 ("Э6", "мутации", None, [PY, f"{HERE}/mutants.py"], "20 мутаций"),
]


def main():
    только = None
    if "--список" in sys.argv:
        for э, имя, tree, cmd, чем in НАБОРЫ:
            print(f"{э}  {имя:34s} {чем}")
        return 0
    if "--только" in sys.argv:
        только = sys.argv[sys.argv.index("--только") + 1]
    моё = СВОЁ if os.path.isdir(СВОЁ) else РЕПО
    if "--дерево" in sys.argv:
        v = sys.argv[sys.argv.index("--дерево") + 1]
        моё = {"репо": РЕПО, "своё": СВОЁ}.get(v, os.path.abspath(v))
    print(f"дерево для проверок Э6: {моё}")
    print(f"слой: {'быстрый + МЕДЛЕННЫЙ' if os.environ.get('E6_SLOW') == '1' else 'быстрый (E6_SLOW=1 добавит книги)'}")
    env = dict(os.environ)
    env["PATH"] = ОБЁРТКА + os.pathsep + env["PATH"]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONWARNINGS", "ignore")
    env.setdefault("E1_PANDOC_CAP", "2000M")
    плохо, строки = 0, []
    for э, имя, tree, cmd, чем in НАБОРЫ:
        if только and только not in (э, имя):
            continue
        e = dict(env)
        e["BOOKSMITH_SRC"] = tree or моё
        if not os.path.exists(cmd[1]):
            строки.append((э, имя, "НЕТ ФАЙЛА", 0, cmd[1]))
            плохо = 1
            continue
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=E6)
        dt = time.time() - t0
        вывод = (r.stdout + r.stderr)
        провалы = [l for l in вывод.split("\n")
                   if l.startswith(("FAIL:", "ERROR:", "ПРОВАЛ", "  ПАДЕНИЕ",
                                    "НЕ ЛОВИТСЯ"))]
        if r.returncode:
            плохо = 1
        строки.append((э, имя, "прошло" if not r.returncode else "УПАЛО",
                       dt, "; ".join(x.strip()[:70] for x in провалы[:4])))
        if r.returncode:
            print(f"----- {э} {имя}: код {r.returncode}")
            print("\n".join(вывод.split("\n")[-25:]))
    print()
    print(f"{'этап':5s} {'набор':34s} {'итог':8s} {'с':>6s}  что упало")
    for э, имя, итог, dt, что in строки:
        print(f"{э:5s} {имя:34s} {итог:8s} {dt:6.1f}  {что}")
    всего = sum(x[3] for x in строки)
    print(f"\nвсего {всего:.1f} с; "
          + ("ЕСТЬ УПАВШИЕ" if плохо else "все прошли"))
    return плохо


if __name__ == "__main__":
    sys.exit(main())
