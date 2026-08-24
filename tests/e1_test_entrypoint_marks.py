# -*- coding: utf-8 -*-
"""Граница пометки в entrypoint.py: та же чётность, но на месте постановки."""
import sys, os, re
sys.path.insert(0, os.path.expanduser("~/booksmith-work/e1/src2"))
sys.path.insert(0, os.path.expanduser(
    "~/booksmith-work/e1/src2/booksmith/jobs/paddleocr"))
import importlib.util
spec = importlib.util.spec_from_file_location("ep", os.path.expanduser(
    "~/booksmith-work/e1/src2/booksmith/jobs/paddleocr/entrypoint.py"))
ep = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(ep)
except Exception as e:      # у задания есть тяжёлые зависимости — берём исходник
    src = open(os.path.expanduser(
        "~/booksmith-work/e1/src2/booksmith/jobs/paddleocr/entrypoint.py"),
        encoding="utf-8").read()
    ns = {}
    exec(src[src.index("def _slash_run("):src.index("def _probe_hallucination(")], ns)
    ep = type("ns", (), ns)

ok = bad = 0
def t(name, got, exp):
    global ok, bad
    if got == exp: ok += 1
    else:
        bad += 1
        print(f"ПРОВАЛ {name}: получили {got!r}, ждали {exp!r}")

t("серия 0", ep._slash_run("abc", 3), 0)
t("серия 1", ep._slash_run("a\\bc", 2), 1)
t("серия 2", ep._slash_run("a\\\\bc", 3), 2)
t("серия 3", ep._slash_run("\\\\\\x", 3), 3)
t("серия в начале строки", ep._slash_run("\\x", 1), 1)
t("i=0", ep._slash_run("\\x", 0), 0)

MARK_MIN_SPAN = 2
def place(out, a, b):
    """Тот же цикл границ, что в entrypoint.py."""
    while a > 0 and ep._slash_run(out, a) % 2: a -= 1
    while b > a and ep._slash_run(out, b) % 2: b -= 1
    if b - a < MARK_MIN_SPAN: return out
    if "\n\n" in out[a:b]: return out
    if out[a:b].strip() and "<" not in out[a:b]:
        return out[:a] + '<mark title="модель не уверена">' + out[a:b] + "</mark>" + out[b:]
    return out

s = "$t_{\\lambda}$"
t("б: начало после слэша уезжает влево",
  place(s, s.index("lambda"), s.index("lambda") + 6),
  '$t_{<mark title="модель не уверена">\\lambda</mark>}$')
s = "реакция \\Phi(x)"
t("а: конец на слэше уезжает влево",
  place(s, 0, s.index("Phi")),
  '<mark title="модель не уверена">реакция </mark>\\Phi(x)')
s = "конец строки\\\\Phi"
t("чётность: `\\\\` границу не двигает",
  place(s, 0, 12),
  '<mark title="модель не уверена">конец строки</mark>\\\\Phi')
s = "первый кусок\n\nвторой кусок"
t("в: спан через пустую строку не ставится", place(s, 0, len(s)), s)
s = "обычный текст тут"
t("здоровый спан ставится как раньше",
  place(s, 8, 13),
  'обычный <mark title="модель не уверена">текст</mark> тут')

print(f"\nпройдено {ok}, провалено {bad}")
sys.exit(1 if bad else 0)
