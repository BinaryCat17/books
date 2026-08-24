# -*- coding: utf-8 -*-
"""Код возврата не теряется: этап -> run.json -> отчёт -> оболочка.

Три места, где он терялся, и все три проверяются здесь на подставках:

  1. `books ocr` не звал `convert` вовсе — форматы не собирались, код 0;
  2. в `run.json` не было поля под код этапа — след не оставался нигде;
  3. `_restructure_after` ловил исключение и возвращал 0 ЯВНО.

Плюс четвёртое, найденное заодно: `books progress` возвращал 0 даже когда
печатал «!! разбор завершился с кодом 1».
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BOOKSMITH_SRC") or os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

ЖУРНАЛ_ЦЕЛЫЙ = """\
[10:00:00] === проход 1 из 1 -> processed/подставка
[10:00:01] снимаю #12345 за $0.400/час
[10:00:02] заливаю входные файлы...
[10:00:05] запускаю задачу...
[10:00:06] === разбираю input.pdf ===
[10:00:40] посчитано 10 страниц за 34с (0.29 стр/с)
[10:00:41] забираю результат целиком...
[10:00:50] итого 0.9 мин ≈ $0.01
"""

# Строка ровно та, какую пишет run.sh на машине.  Первая редакция шаблона в
# `cmd_progress` искала «завершился с кодом» и эту строку не видела вовсе —
# нашлось этой подставкой.
ЖУРНАЛ_С_БЕДОЙ = ЖУРНАЛ_ЦЕЛЫЙ + "[10:00:51] разбор завершён с кодом 1\n"
# А это НЕ беда: успешный прогон пишет ту же строку с нулём.
ЖУРНАЛ_УСПЕХ = ЖУРНАЛ_ЦЕЛЫЙ + "[10:00:51] разбор завершён с кодом 0\n"


def main():
    from booksmith import layout, cli, structure

    беды = []
    tmp = tempfile.mkdtemp(prefix="e7-rc-")
    try:
        # 1. record_stage оставляет след в run.json.
        layout.record_stage(tmp, "свод", 0)
        layout.record_stage(tmp, "структура", 3, "нет json страниц")
        d = json.load(io.open(os.path.join(tmp, "run.json"), encoding="utf-8"))
        print("run.json после двух этапов:",
              json.dumps(d.get("этапы"), ensure_ascii=False))
        if not d.get("этапы"):
            беды.append("record_stage не записал ничего")
        плохо = layout.failed_stages(tmp)
        print(f"  этапов с ненулевым кодом: {len(плохо)} ({', '.join(плохо)})")
        if set(плохо) != {"структура"}:
            беды.append(f"failed_stages вернул {set(плохо)}, ждали "
                        "{'структура'}")

        # 2. `_restructure_after` на упавшей сборке НЕ возвращает 0.
        было = structure.restructure
        try:
            structure.restructure = lambda _o: (_ for _ in ()).throw(
                RuntimeError("нет json страниц"))
            rc = cli._restructure_after(tmp)
        finally:
            structure.restructure = было
        print(f"  _restructure_after на упавшей сборке -> код {rc}")
        if rc == 0:
            беды.append("_restructure_after проглотил исключение и вернул 0")

        # 3. `_convert_after` — то же самое, и он вообще вызывается.
        from booksmith import convert as conv
        было_c = conv.convert
        try:
            conv.convert = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("pandoc не найден"))
            rc = cli._convert_after(tmp)
        finally:
            conv.convert = было_c
        print(f"  _convert_after на упавшей сборке -> код {rc}")
        if rc == 0:
            беды.append("_convert_after проглотил исключение и вернул 0")
        if "форматы" not in layout.stages(tmp):
            беды.append("этап «форматы» не записан в run.json")

        # 4. Книга с ненулевым кодом называет себя неготовой в отчёте.
        текст = "\n".join(structure.кончилась_сборка(tmp))
        первая = текст.splitlines()[2] if len(текст.splitlines()) > 2 else ""
        print("  первая строка раздела отчёта:", первая[:70])
        if "НЕ ГОТОВА" not in текст:
            беды.append("отчёт не назвал книгу неготовой при ненулевом коде")

        # И наоборот: когда всё нулевое, слова «НЕ ГОТОВА» быть не должно.
        чистый = tempfile.mkdtemp(prefix="e7-rc-ok-")
        layout.record_stage(чистый, "свод", 0)
        layout.record_stage(чистый, "структура", 0)
        layout.record_stage(чистый, "форматы", 0)
        если_всё_хорошо = "\n".join(structure.кончилась_сборка(чистый))
        if "НЕ ГОТОВА" in если_всё_хорошо:
            беды.append("отчёт назвал неготовой книгу без единого ненулевого кода")
        else:
            print("  на нулевых кодах отчёт про неготовность молчит — верно")
        # И на старом разборе, где этапов нет, отчёт говорит «не записано»,
        # а не «всё хорошо».
        пустой = tempfile.mkdtemp(prefix="e7-rc-old-")
        стар = "\n".join(structure.кончилась_сборка(пустой))
        if "Не записано" not in стар:
            беды.append("на разборе без этапов отчёт не сказал «не записано»")
        else:
            print("  на разборе без этапов отчёт говорит «не записано» — верно")
        shutil.rmtree(чистый, ignore_errors=True)
        shutil.rmtree(пустой, ignore_errors=True)

        # 5. `books progress` возвращает 1 на журнале с бедой и 0 на целом.
        class A:
            def __init__(self, p):
                self.path = p
        for имя, текст_ж, ждём in (("целый", ЖУРНАЛ_ЦЕЛЫЙ, 0),
                                   ("успех с кодом 0", ЖУРНАЛ_УСПЕХ, 0),
                                   ("с бедой", ЖУРНАЛ_С_БЕДОЙ, 1)):
            p = os.path.join(tmp, f"{имя}.log")
            io.open(p, "w", encoding="utf-8").write(текст_ж)
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.cmd_progress(A(p))
            print(f"  books progress на журнале «{имя}» -> код {rc} "
                  f"(ждали {ждём})")
            if rc != ждём:
                беды.append(f"progress на журнале «{имя}» вернул {rc}, "
                            f"а не {ждём}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for x in беды:
        print("  !!", x)
    return 1 if беды else 0


if __name__ == "__main__":
    sys.exit(main())
