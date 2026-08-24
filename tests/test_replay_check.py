# -*- coding: utf-8 -*-
"""`books replay --check` возвращает 1, пока список недостающего непуст.

Проверка нужна с кодом возврата, а не с абзацем в отчёте: заметка «в
run.json надо бы добавить» уже была, и её никто не прочёл.

Мутации, на которых проверка обязана падать, прогоняются сами:
  * из полного слепка вынута одна величина — любая из 41;
  * величина есть, но пустая (`null`) — это ЗАКОННО и падать не должно:
    «системного сообщения нет» — ответ, а не пропуск;
  * пустой `run.json` — не хватает всего.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BOOKSMITH_SRC") or os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.abspath(SRC))


def полный_слепок(req):
    """Собрать слепок, в котором есть ровно всё требуемое."""
    d = {}
    for path, _what in req:
        cur = d
        for k in path[:-1]:
            cur = cur.setdefault(k, {})
        cur[path[-1]] = None            # null — законное значение
    return d


def main():
    from booksmith import replay

    req = replay.required()
    беды = []
    print(f"в реестре величин: {len(req)}")

    tmp = tempfile.mkdtemp(prefix="e7-replay-")
    try:
        def записать(d):
            with open(os.path.join(tmp, "run.json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            return tmp

        # 1. Полный слепок: не хватает ноль, код возврата 0.
        полный = полный_слепок(req)
        нет = replay.check(записать(полный), verbose=False)
        print(f"  полный слепок (все значения null): не хватает {len(нет)}")
        if нет:
            беды.append(f"полный слепок объявлен неполным: {нет[:3]}")

        # 2. Пустой run.json: не хватает всего.
        нет = replay.check(записать({}), verbose=False)
        print(f"  пустой run.json: не хватает {len(нет)} из {len(req)}")
        if len(нет) != len(req):
            беды.append("пустой слепок не объявлен пустым")

        # 3. Каждая величина по отдельности: вынули — обязано заметить.
        пропущено = []
        for path, _what in req:
            d = json.loads(json.dumps(полный))
            cur = d
            for k in path[:-1]:
                cur = cur[k]
            del cur[path[-1]]
            нет = replay.check(записать(d), verbose=False)
            if not any(p == path for p, _ in нет):
                пропущено.append("/".join(map(str, path)))
        print(f"  вынимали по одной величине: замечено "
              f"{len(req) - len(пропущено)} из {len(req)}")
        if пропущено:
            беды.append("не замечено вынимание: " + ", ".join(пропущено[:5]))

        # 4. Код возврата команды.
        class A:
            outdir = [tmp]
            check = True
        записать({})
        rc = replay.cmd_replay(A())
        записать(полный)
        rc0 = replay.cmd_replay(A())
        print(f"  код возврата: пустой слепок -> {rc}, полный -> {rc0}")
        if rc != 1:
            беды.append(f"на пустом слепке код возврата {rc}, а не 1")
        if rc0 != 0:
            беды.append(f"на полном слепке код возврата {rc0}, а не 0")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 5. На настоящих разборах: сколько не хватает сегодня.
    для_настоящих = os.environ.get("BOOKS_ROOT", "/home/smirn/books")
    proc = os.path.join(для_настоящих, "processed")
    if os.path.isdir(proc):
        print("\nна настоящих разборах (репозиторий не изменяется):")
        for b in sorted(os.listdir(proc)):
            d = os.path.join(proc, b)
            if os.path.isfile(os.path.join(d, "run.json")):
                print(f"  {b:17s} не хватает "
                      f"{len(replay.check(d, verbose=False))} из {len(req)}")

    for x in беды:
        print("  !!", x)
    return 1 if беды else 0


if __name__ == "__main__":
    sys.exit(main())
