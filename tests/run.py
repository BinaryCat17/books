"""Бегун проверок: без сети, без GPU, без аренды.

    /home/smirn/books/.venv/bin/python tests/run.py              все проверки
    /home/smirn/books/.venv/bin/python tests/run.py --selfcheck  батарея мутаций
    /home/smirn/books/.venv/bin/python tests/run.py --slow       и медленные
    /home/smirn/books/.venv/bin/python tests/run.py test_swap    один файл

pytest в `.venv` НЕТ, поэтому бегун свой, но проверки написаны так, что pytest
их подберёт без правок: файлы `test_*.py`, функции `test_*`, обычный `assert`.

ПЕЧАТАЕТСЯ ВЕЛИЧИНА, А НЕ СЛОВО «ГОТОВО»: сколько проверок прошло, сколько
провалено, сколько ПРОПУЩЕНО и почему, и сколько секунд это заняло. Пропуск
считается отдельным числом нарочно — ноль от проверки и ноль от непонимания
разные нули, и «пропущено 5» в строке итога видно так же, как провал.

`--selfcheck` — та же мысль, что у `metrics.mutations()`: проверка обязана
уметь провалиться. Батарея ломает проверяемое место (в памяти или в КОПИИ
исходника, рабочее дерево не трогается) и требует, чтобы названная проверка
покраснела. Мутация, которую никто не поймал, печатается как НЕ ПОЙМАНА и
роняет прогон: зелёная проверка на сломанном коде хуже отсутствующей.
"""
import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import support                                              # noqa: E402
from support import Skip                                    # noqa: E402

# ЭТОТ БЕГУН ОБЪЯВЛЯЕТ СЕБЯ, и делает это до загрузки первого файла проверок.
# `support.skip()` выбирает форму пропуска по тому, КТО ГОНЯЕТ; прежде он
# выбирал по тому, что УСТАНОВЛЕНО («импортируется ли pytest»), и стоило бы
# это всего прогона — см. `support.foreign_skip`.
support.OWN_RUNNER = True

SLOW = "BOOKSMITH_TESTS_SLOW"


def load(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def files(only):
    out = []
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py"):
            if only and not any(o in fn for o in only):
                continue
            out.append(os.path.join(HERE, fn))
    return out


def cases(mod):
    return [(n, getattr(mod, n)) for n in sorted(vars(mod))
            if n.startswith("test_") and callable(getattr(mod, n))]


def run_case(fn):
    """(состояние, причина/след). Состояния три, и они разные."""
    try:
        fn()
        return "ok", ""
    except Skip as e:
        return "skip", str(e)
    except (Exception, SystemExit):
        # SystemExit не Exception: отказ адаптера («нет пакета docling»,
        # «неизвестный режим») прилетает именно им, и проглотить его значило
        # бы уронить бегун вместо того, чтобы напечатать провал.
        return "fail", traceback.format_exc()
    except BaseException as e:
        # Всё, что не Exception и не SystemExit: чужой пропуск засчитываем
        # пропуском, остальное (KeyboardInterrupt, MemoryError) отдаём наружу
        # — глотать Ctrl+C значило бы сделать бегун неостановимым.
        #
        # Что считать чужим пропуском, решает ОДИН дом — `support`, рядом с
        # нашим `Skip`. Зовётся через модуль, а не по имени: батарея мутаций
        # ломает проверяемое место В ПАМЯТИ, и без этого шва проба «бегун не
        # знает чужого пропуска» не накладывалась бы вовсе.
        if support.foreign_skip(e):
            return "skip", f"{e} (объявлен через pytest.skip)"
        raise


def main(argv):
    only = [a for a in argv if not a.startswith("-")]
    if "--slow" in argv:
        os.environ[SLOW] = "1"
    t0 = time.time()
    ok = failed = skipped = 0
    bad, skips = [], []
    for path in files(only):
        mod = load(path)
        base = os.path.basename(path)
        for name, fn in cases(mod):
            t = time.time()
            state, why = run_case(fn)
            dt = time.time() - t
            mark = {"ok": "  ", "skip": "  ПРОПУСК", "fail": "  ПРОВАЛ"}[state]
            print(f"{mark} {base}::{name}  {dt:.3f}с"
                  + (f"  — {why}" if state == "skip" else ""))
            if state == "ok":
                ok += 1
            elif state == "skip":
                skipped += 1
                skips.append(f"{base}::{name} — {why}")
            else:
                failed += 1
                bad.append((f"{base}::{name}", why))
    for name, tb in bad:
        print(f"\n--- ПРОВАЛ {name} ---\n{tb}")
    print(f"\nпроверок {ok + failed + skipped}: прошло {ok}, провалено "
          f"{failed}, пропущено {skipped}; {time.time() - t0:.1f}с")
    if skipped and not bad:
        print("пропущенное НЕ проверено ничем: " + "; ".join(skips))
    rc = 1 if failed else 0
    if "--selfcheck" in argv:
        import selfcheck
        rc = selfcheck.main() or rc
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
