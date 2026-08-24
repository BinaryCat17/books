# -*- coding: utf-8 -*-
"""Мутации: порча кода и проверка, что приёмка её ловит.

Тест, не падающий ни на одной мутации, — фон, а не проверка.  Здесь для
каждой правки Э1 записана мутация, которая её отменяет, и рядом печатается,
какие проверки на ней упали.
"""
import os, re, shutil, subprocess, sys, tempfile

BASE = os.path.expanduser("~/booksmith-work/e1/src2")
TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_convert.py")

MUT = [
 ("1. вернуть raw_tex",
  '"-raw_tex-superscript-subscript-native_divs"',
  '"-superscript-subscript-native_divs"'),
 ("2. вернуть superscript/subscript",
  '"-raw_tex-superscript-subscript-native_divs"',
  '"-raw_tex-native_divs"'),
 ("9. вернуть native_divs",
  '"-raw_tex-superscript-subscript-native_divs"',
  '"-raw_tex-superscript-subscript"'),
 ("3. вернуть strip(\" {}\") в army()",
  "cells = [x for x in (_unbrace(c) for c in r.split(\"&\")) if x]",
  "cells = [c.strip(\" {}\") for c in r.split(\"&\") if c.strip(\" {}\")]"),
 ("4а. снять проверку чётности слэшей",
  'r"(?<!\\\\)((?:\\\\\\\\)*)\\\\(</?mark',
  'r"()\\\\(</?mark'),
 ("4в. не перевыставлять пометку через абзац",
  '        if pending:\n            buf.append("</mark>")\n            stat["пометка перевыставлена через абзац"] += 1',
  '        if pending:\n            pass'),
 ("5. не дописывать висячие скобки",
  "        if depth > 0:\n            part = part + \"}\" * depth",
  "        if False:\n            part = part + \"}\" * depth"),
 ("7. не печатать величину провала",
  "    import difflib\n    a = _tables(src_text)",
  "    return (0, None, \"\")\n    import difflib\n    a = _tables(src_text)"),
 ("4б. чинить только закрывающий тег",
  'r"(?<!\\\\)((?:\\\\\\\\)*)\\\\(</?mark',
  'r"(?<!\\\\)((?:\\\\\\\\)*)\\\\(</mark'),
 ("6. сверять epub по тегам, а не по файлам",
  "want_epub = dict(want, картинок=want_files)",
  "want_epub = want"),
 ("8. вернуть короткое замыкание в rc",
  "            if not _report(f\"{os.path.relpath(html_path)} \"",
  "            if rc or not _report(f\"{os.path.relpath(html_path)} \""),
]

def run(src):
    r = subprocess.run([sys.executable, TEST, src], capture_output=True, text=True)
    fails = [l for l in r.stdout.splitlines() if l.startswith("ПРОВАЛ")]
    return r.returncode, fails

rc, fails = run(BASE)
print(f"=== целый код: код возврата {rc}, провалов {len(fails)}")
assert rc == 0, "приёмка не проходит на неиспорченном коде — чинить её"

worst = 0
for name, a, b in MUT:
    d = tempfile.mkdtemp()
    dst = os.path.join(d, "src")
    shutil.copytree(BASE, dst)
    p = os.path.join(dst, "booksmith", "convert.py")
    s = open(p, encoding="utf-8").read()
    if s.count(a) < 1:
        print(f"!!! мутация «{name}» не наложилась — искали {a[:40]!r}")
        worst = 1
        shutil.rmtree(d, ignore_errors=True)
        continue
    open(p, "w", encoding="utf-8").write(s.replace(a, b, 1))
    rc, fails = run(dst)
    mark = "ловится" if rc != 0 else "НЕ ЛОВИТСЯ"
    print(f"{mark:10s} {name}: упало {len(fails)} — "
          + ", ".join(f.split()[1] for f in fails[:6]))
    if rc == 0:
        worst = 1
    shutil.rmtree(d, ignore_errors=True)
sys.exit(worst)
