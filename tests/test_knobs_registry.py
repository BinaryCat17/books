# -*- coding: utf-8 -*-
"""Реестр ручек — единственное место, откуда читается окружение.

Проверка разбирает ИСХОДНИК деревом, а не гоняет код: ветка
`if os.environ.get("PROBE") == "1"` на подставке не исполняется никогда, и
проверка поведением её не увидит.  Разбор видит.

Что она ловит (мутации, на которых она падает, перечислены в
`МУТАЦИИ` внизу файла и прогоняются сами):

  * `os.environ.get("НОВАЯ_РУЧКА", ...)` где-нибудь в entrypoint.py;
  * `export НОВАЯ=…` в run.sh — так в прошлый раз поймался `VL_MODEL_DIR`:
    ручку ставит оболочка, в entrypoint.py её не видно, а решает она, какие
    веса поднимет vLLM;
  * `def knob(name, default=None)` — второе место жительства умолчания;
  * `_PASS`, выписанный руками, а не собранный из реестра.
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BOOKSMITH_SRC") or os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

JOB = os.path.join(os.path.abspath(SRC), "booksmith", "jobs", "paddleocr")
ENTRY = os.path.join(JOB, "entrypoint.py")
RUNSH = os.path.join(JOB, "run.sh")

# Переменные, которые run.sh ставит СЕБЕ и своим детям как обстановку, а не
# как ручку разбора: их значение вычисляется тут же и в слепок не просится.
# Список именной нарочно: молчаливое «ну это же системная» и есть та щель, в
# которую утёк VL_MODEL_DIR.
ОБСТАНОВКА = {"PATH", "VIRTUAL_ENV", "CUDA_HOME"}


def env_reads(source):
    """Все чтения окружения в исходнике: (имя, строка). Дерево, не регулярка."""
    got = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # os.environ.get("X"), os.getenv("X")
        if isinstance(f, ast.Attribute) and f.attr in ("get", "setdefault"):
            v = f.value
            if (isinstance(v, ast.Attribute) and v.attr == "environ") and node.args:
                if isinstance(node.args[0], ast.Constant):
                    got.append((node.args[0].value, node.lineno))
        if isinstance(f, ast.Attribute) and f.attr == "getenv" and node.args:
            if isinstance(node.args[0], ast.Constant):
                got.append((node.args[0].value, node.lineno))
    # os.environ["X"]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript):
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "environ":
                sl = node.slice
                if isinstance(sl, ast.Constant):
                    got.append((sl.value, node.lineno))
    return got


def sh_exports(source):
    """Что run.sh кладёт в окружение задачи или сам берёт из окружения.

    Два признака, и оба механические — «ну это же просто переменная» и есть
    та щель, в которую утёк VL_MODEL_DIR:

      * `export NAME=…` — попадает в окружение entrypoint.py;
      * `${NAME:-умолчание}` — читается из окружения, то есть у ручки уже
        появилось второе место жительства умолчания, в оболочке.

    Из второго списка выкидываются имена, которым оболочка присваивает
    значение сама (`SRV=$!`): это местные переменные скрипта, снаружи их
    никто не задаёт.  Экспортируемые остаются даже если присвоены здесь же —
    `export VL_MODEL_DIR=/models/vl` именно так и выглядит.
    """
    экспорт = set(re.findall(r"^\s*export\s+([A-Z_][A-Z0-9_]*)=", source, re.M))
    свои = set(re.findall(r"^\s*([A-Z_][A-Z0-9_]*)=", source, re.M)) - экспорт
    читает = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*):-", source))
    return экспорт | (читает - свои)


def проверить(строгая_подстановка=None):
    """Вернуть список нарушений. Пусто — реестр полон."""
    from booksmith.jobs.paddleocr.entrypoint import KNOBS, knob
    from booksmith.jobs import paddleocr as job

    зарегистрированы = {k.name for k in KNOBS}
    беды = []

    src = строгая_подстановка or io.open(ENTRY, encoding="utf-8").read()
    # 1. Каждое чтение окружения в entrypoint.py — только внутри knob().
    knob_line = None
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "knob":
            knob_line = (node.lineno, max(getattr(n, "lineno", node.lineno)
                                          for n in ast.walk(node)))
            # 3. У knob() не должно быть параметра default.
            имена = [a.arg for a in node.args.args] + \
                    [a.arg for a in node.args.kwonlyargs]
            if "default" in имена or node.args.defaults or node.args.kw_defaults:
                беды.append("у knob() появилось умолчание в подписи: "
                            "умолчаний становится два — в реестре и в вызове")
    for имя, строка in env_reads(src):
        if knob_line and knob_line[0] <= строка <= knob_line[1]:
            continue                     # это и есть само чтение внутри knob()
        if имя not in зарегистрированы:
            беды.append(f"entrypoint.py:{строка} читает окружение мимо реестра: "
                        f"{имя!r} — объяви его в KNOBS")
        else:
            беды.append(f"entrypoint.py:{строка}: {имя!r} читается напрямую, "
                        f"а не через knob() — умолчание разъедется с реестром")

    # 2. Всё, что run.sh кладёт в окружение задачи, тоже ручка.
    for имя in sorted(sh_exports(io.open(RUNSH, encoding="utf-8").read())):
        if имя in ОБСТАНОВКА or имя in зарегистрированы:
            continue
        беды.append(f"run.sh ставит {имя}, а в KNOBS его нет: ручка, которой "
                    f"не видно в entrypoint.py, тем более обязана быть в слепке")

    # 4. Список проброса собран из реестра, а не выписан руками.
    if set(job._PASS) != зарегистрированы:
        беды.append(f"_PASS разошёлся с реестром: в нём {len(job._PASS)} имён, "
                    f"в KNOBS {len(зарегистрированы)}")

    # 5. knob() на незнакомое имя обязан ругаться, а не возвращать пустоту.
    try:
        knob("ЧЕГО_НЕТ_В_РЕЕСТРЕ")
        беды.append("knob() принял незнакомое имя молча")
    except KeyError:
        pass
    return беды


# ------------------------------------------------------------------ мутации
# Тест, не падающий ни на одной мутации, — фон, а не проверка.
МУТАЦИИ = [
    ("новое чтение окружения мимо реестра",
     lambda s: s.replace("def _log(msg):",
                         'НОВОЕ = os.environ.get("СОВСЕМ_НОВАЯ_РУЧКА", "1")\n\n\ndef _log(msg):', 1)),
    ("ручка из реестра, но читаемая напрямую",
     lambda s: s.replace('if knob("PREFER_TABLES") == "1":',
                         'if os.environ.get("PREFER_TABLES", "1") == "1":', 1)),
    ("os.environ[...] вместо knob()",
     lambda s: s.replace("def _log(msg):",
                         'НОВОЕ = os.environ["ЕЩЁ_ОДНА"]\n\n\ndef _log(msg):', 1)),
]


def main():
    беды = проверить()
    for b in беды:
        print("  !!", b)
    print(("реестр полон: нарушений нет" if not беды
           else f"НАРУШЕНИЙ {len(беды)}"))
    print("\nмутации, на которых проверка обязана падать:")
    целый = io.open(ENTRY, encoding="utf-8").read()
    все_поймано = True
    for имя, порча in МУТАЦИИ:
        поймано = проверить(порча(целый))
        новые = [x for x in поймано if x not in беды]
        ok = bool(новые)
        все_поймано &= ok
        print(f"  {'ловит' if ok else 'ПРОПУСКАЕТ':10s}  {имя}"
              + (f"  ->  {новые[0][:80]}" if новые else ""))
    return 0 if (not беды and все_поймано) else 1


if __name__ == "__main__":
    sys.exit(main())
