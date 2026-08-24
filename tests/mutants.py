# -*- coding: utf-8 -*-
"""Мутации: нарочная порча кода и проверка, что приёмка её ловит.

Тест, не падающий ни на одной мутации, — фон, а не проверка.  В этом проекте
так уже было: пометка `≠` стояла у 416 таблиц из 448 и ничего не значила.

Каждая строка ниже — правка, отменённая обратно, и набор, который обязан от
этого покраснеть.  Дерево названо у каждой мутации своё: правку Э3 нельзя
отменить в исходнике, где её нет.

Запуск: python3 tests/mutants.py [номер …]
Возврат 1, если хоть одна мутация не поймана.
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
E6 = os.path.dirname(HERE)
W = os.path.expanduser("~/booksmith-work")
БАЗА = "/home/smirn/books/src"
PY = "/home/smirn/books/.venv/bin/python"
if not os.path.exists(PY):
    PY = sys.executable

# (имя, дерево, файл, что искать, чем заменить, какие наборы обязаны упасть)
МУТАЦИИ = [
 ("М1 резать имя по знакам, а не по байтам", БАЗА, "layout.py",
  "    b = stem.encode(\"utf-8\")\n    if len(b) > limit:\n"
  "        stem = b[:limit].decode(\"utf-8\", \"ignore\")",
  "    if len(stem) > limit:\n        stem = stem[:limit]",
  ["test_safe_name.py"]),

 ("М2 не обезвреживать служебное имя", БАЗА, "layout.py",
  "    if stem.casefold() in RESERVED:\n        stem += \"_книга\"",
  "    if False:\n        stem += \"_книга\"",
  ["test_safe_name.py"]),

 ("М3 прогнать хранимое имя через splitext (откусить том)", БАЗА, "layout.py",
  "    stem = re.sub(r\"[\\s]+\", \"_\", str(stem).strip())",
  "    stem = os.path.splitext(str(stem))[0]\n"
  "    stem = re.sub(r\"[\\s]+\", \"_\", str(stem).strip())",
  ["test_safe_name.py", "test_tidy.py"]),

 ("М4 не снимать абзацную пометку перед проверкой переноса", БАЗА, "structure.py",
  "            m = PROSE_TAIL.search(cur)",
  "            m = None",
  ["test_perenos.py"]),

 ("М5 не возвращать пометку в конец склеенного абзаца", БАЗА, "structure.py",
  "                    if m and not PROSE_TAIL.search(glued):\n"
  "                        glued += \" ≠\"",
  "                    if False:\n                        glued += \" ≠\"",
  ["test_perenos.py"]),

 ("М6 склеивать переносы в один проход, а не до неподвижности", БАЗА, "structure.py",
  "        text = \"\\n\".join(out)\n        n += hit\n        if not hit:\n"
  "            return text, n",
  "        text = \"\\n\".join(out)\n        n += hit\n        return text, n",
  ["test_perenos.py", "test_idempotent.py"]),

 ("М7 терять хвост слова при склейке переноса", БАЗА, "structure.py",
  "                    glued = head[:-1] + lines[j].lstrip()",
  "                    glued = head[:-1]",
  ["test_ne_ubylo.py", "test_perenos.py"]),

 ("М8 не возвращать таблицы после защиты", БАЗА, "structure.py",
  "def _restore(text, kept):\n    return re.sub",
  "def _restore(text, kept):\n    return text\n    return re.sub",
  ["test_ne_ubylo.py"]),

 ("М9 дописывать абзацное ≠ второй и третий раз", БАЗА, "merge.py",
  "        if part.rstrip().endswith(\"≠\"):",
  "        if False:",
  ["test_idempotent.py"]),

# М10 «метить ячейку за кратность» снята как ОТЖИВШАЯ, а не как ненужная.
# Она мутировала строку `if all(w[v] >= k for w in whole)` в дереве БАЗА, то
# есть в репозитории ДО применения правок.  Правка Э3 переписала это место
# целиком (`if all(k in keys for keys, _ in wit)`), и прежней строки в
# репозитории больше нет — мутация перестала ложиться.
#
# Тот же признак проверяет М16 на том же самом коде: возврат к сличению по
# мультимножеству ловится `test_pometki.py`.  Подгонять М10 под новый текст
# значило бы держать в наборе две одинаковые мутации ради круглого счёта.

 ("М11 не приводить запятую к точке в числах", БАЗА, "merge.py",
  "        x = x.replace(\",\", \".\")      # `0,5` и `0.5` — одно число",
  "        pass",
  ["test_pometki.py"]),

 ("М12 заходить пометкой внутрь формулы", БАЗА, "merge.py",
  "    holes += [(m.start(), m.end()) for m in MATH.finditer(text)]",
  "    holes += []",
  ["test_pometki.py"]),

 ("М13 брать имя книги из имени каталога, а не из pdf", БАЗА, "cli.py",
  "    stem = layout.clean_stem(pdf)",
  "    stem = layout.clean_stem(out)",
  ["test_tidy.py"]),

 ("М14 сносить в book/ всё подряд, а не только своё", БАЗА, "cli.py",
  "            if name in DRAFTS or name == \"imgs\":",
  "            if True:",
  ["test_tidy.py"]),

 # ---- правки этапов: мутация отменяет правку в дереве этапа ---------------
 ("М15 (Э3) вернуть выход по пустой ячейке ДО знаменателя",
  os.path.join(W, "e3", "src2"), "merge.py",
  "            v = plain(m.group(2))\n            total += 1",
  "            v = plain(m.group(2))\n            if not v:\n"
  "                return m.group(0)\n            total += 1",
  ["test_pometki.py"]),

 ("М16 (Э3) вернуть сличение по мультимножеству",
  os.path.join(W, "e3", "src2"), "merge.py",
  "            k = cell_key(v)\n            if all(k in keys for keys, _ in wit):",
  "            k = cell_key(v)\n            if all(k in keys for keys, _ in wit) "
  "and not v.endswith(\"0\"):",
  ["test_pometki.py"]),

 ("М17 (Э3) снести всю пунктуацию в ключе ячейки",
  os.path.join(W, "e3", "src2"), "merge.py",
  "def cell_key(v):",
  "def cell_key(v):\n    return \"\".join(c for c in v if c.isalnum()).casefold()",
  ["test_pometki.py"]),

 ("М18 (Э3) не помнить, что ячейка уже помечена",
  os.path.join(W, "e3", "src2"), "merge.py",
  "            if m.group(2).rstrip().endswith(\"≠\"):",
  "            if False:",
  ["test_idempotent.py"]),

 ("М19 (Э1) вернуть raw_tex", os.path.join(W, "e1", "src2"), "convert.py",
  '"-raw_tex-superscript-subscript-native_divs"',
  '"-superscript-subscript-native_divs"',
  ["test_convert_stand.py"]),

 ("М20 (Э1) вернуть superscript/subscript", os.path.join(W, "e1", "src2"),
  "convert.py",
  '"-raw_tex-superscript-subscript-native_divs"', '"-raw_tex-native_divs"',
  # Стенд в 12 страниц этого НЕ ловит: ложный `<sup>` рождается на образце
  # `2^10^`, которого в вырезке нет.  Ловит проверка Э1 на подставке — и это
  # ровно тот случай, ради которого рукотворные образцы держат рядом с
  # вырезками, а не вместо них.
  ["e1:test_convert.py"]),
]


def прогнать(tree, наборы, env=None):
    # Мутации гоняются ТОЛЬКО по быстрому слою: на медленном они стоили бы
    # 20 мутаций × минуту вместо 20 × полутора секунд.
    e = dict(os.environ, BOOKSMITH_SRC=tree, PYTHONDONTWRITEBYTECODE="1",
             PYTHONWARNINGS="ignore", E6_SLOW="0")
    e.update(env or {})
    упали = []
    for n in наборы:
        if n.startswith("e1:"):
            # Проверки Э1 — скрипт, дерево берут первым доводом.
            путь = os.path.join(W, "e1", "tests", n[3:])
            r = subprocess.run([PY, "-W", "ignore", путь, tree],
                               capture_output=True, text=True, env=e, cwd=E6)
        else:
            r = subprocess.run([PY, "-W", "ignore", os.path.join(HERE, n)],
                               capture_output=True, text=True, env=e, cwd=E6)
        if r.returncode != 0:
            упали.append(n)
    return упали


def main():
    хочу = set(sys.argv[1:])
    плохо = 0
    print(f"{'мутация':66s} {'ловится?':10s} упавшие наборы")
    for i, (имя, дерево, файл, было, стало, наборы) in enumerate(МУТАЦИИ, 1):
        if хочу and str(i) not in хочу and имя.split()[0] not in хочу:
            continue
        if not os.path.isdir(дерево):
            print(f"{имя:66s} {'НЕТ ДЕРЕВА':10s} {дерево}")
            плохо = 1
            continue
        d = tempfile.mkdtemp(prefix="e6-mut-")
        try:
            dst = os.path.join(d, "src")
            shutil.copytree(дерево, dst, ignore=shutil.ignore_patterns("__pycache__"))
            p = os.path.join(dst, "booksmith", файл)
            s = open(p, encoding="utf-8").read()
            if было not in s:
                print(f"{имя:66s} {'НЕ ЛЕГЛА':10s} искали {было[:48]!r}")
                плохо = 1
                continue
            open(p, "w", encoding="utf-8").write(s.replace(было, стало, 1))
            упали = прогнать(dst, наборы)
            ok = set(упали) == set(наборы)
            печать = "ловится" if упали else "НЕ ЛОВИТСЯ"
            if упали and not ok:
                печать = "частично"
            if not упали:
                плохо = 1
            print(f"{имя:66s} {печать:10s} {', '.join(упали) or '—'}")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return плохо


if __name__ == "__main__":
    sys.exit(main())
