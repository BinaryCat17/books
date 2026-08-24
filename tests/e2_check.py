"""Приёмка Э2.  Каждая проверка названа мутацией, на которой она падает.

Запуск:  python3 tools/check.py [книга …]
Возврат 1, если хоть одна проверка не прошла.
"""
import io, contextlib, os, re, sys
sys.path.insert(0, os.path.expanduser("~/booksmith-work/cc1/src"))
from booksmith import merge as MG

DATA = "/home/smirn/booksmith-work/e2/data"
BOOKS = sys.argv[1:] or ["kristallizaciya", "ogneupory", "chugun",
                         "feynman-1", "biohimiya", "book-new"]
IMGSRC = re.compile(r'src="(imgs/[^"]+)"')
SCAN_ANY = re.compile(r"<!-- (?:скан таблицы:|вырезка таблицы не выгружена:)")
bad = 0


def ok(name, cond, note=""):
    global bad
    print(("  ok   " if cond else "  ПАДЕНИЕ ") + name + (f" — {note}" if note else ""))
    if not cond:
        bad += 1


for b in BOOKS:
    d = os.path.join(DATA, b)
    p = MG.layout.Paths(d)
    passes = p.passes
    book = open(MG.layout.draft_of(passes[0]), encoding="utf-8").read()
    names = MG._pages_by_name(passes[0])
    texts = [open(names[n], encoding="utf-8").read() for n in sorted(names)]
    print(f"===== {b}")

    # 1. Разметка книги по страницам обязана быть разбиением без потерь.
    #    Мутация: убрать `min(cuts[i], cuts[i+1])` в page_spans — разрезы
    #    перестают быть монотонными, кусок книги теряется или задваивается.
    cuts, clean, blines = MG.page_spans(texts, book)
    rebuilt = "".join("".join(blines[cuts[i]:cuts[i + 1]])
                      for i in range(len(texts)))
    ok("разрезы дают книгу прохода 1 байт в байт", rebuilt == book,
       f"{len(rebuilt)} против {len(book)}")

    # 2. Никого не заменили — книга прежняя.
    #    Мутация: заменить `out.append("".join(blines[...]))` на текст
    #    страницы — исчезнут сшивки таблиц и уровни заголовков.
    sv = (MG.looping, MG.ladder, MG.cells_count)
    MG.looping = lambda md: None      # все кандидаты равны, побеждает
    MG.ladder = lambda md: 0                 # проход 1 по номеру
    MG.cells_count = lambda md: 0
    t0, _w, note0 = MG.choose_base(passes, p.imgs)
    MG.looping, MG.ladder, MG.cells_count = sv
    ok("без подмен свод даёт прежний текст байт в байт", t0 == book,
       f"подмен {sum(1 for x in note0['pick'] if x)}")

    # 3. Ни одна величина не убывает.
    #    Мутация: снять охрану слов (KEEP_WORDS = 0) — слова убудут на 11 046.
    text, wits, note = MG.choose_base(passes, p.imgs)
    ok("непустых ячеек не убыло",
       note["cells_new"] >= note["cells_base"],
       f"{note['cells_base']} -> {note['cells_new']}")
    ok("слов не убыло больше чем на 0.3%",
       note["words_new"] >= 0.997 * note["words_base"],
       f"{note['words_base']} -> {note['words_new']}")
    ok("таблиц не убыло",
       len(MG.TABLE.findall(text)) >= len(MG.TABLE.findall(book)),
       f"{len(MG.TABLE.findall(book))} -> {len(MG.TABLE.findall(text))}")
    ok("тегов картинок не убыло",
       len(re.findall(r"<img\b", text)) >= len(re.findall(r"<img\b", book)))

    # 4. Слова на НЕзацикленных страницах не убывают.
    #    Мутация: KEEP_WORDS = 0.5 — усечённые страницы начнут выигрывать,
    #    и этот счёт уйдёт в минус.
    all_names = sorted(names)
    per = [MG._pages_by_name(x) for x in passes]
    tx = [{n: open(f, encoding="utf-8").read() for n, f in m.items()}
          for m in per]
    wb = wn = 0
    for i, n in enumerate(all_names):
        base = tx[0][n]
        chosen = None
        for k in range(len(passes)):
            if n in tx[k] and tx[k][n].rstrip("\n") + "\n\n" in text:
                chosen = tx[k][n]
        if MG.looping(base) or (chosen and MG.looping(chosen)):
            continue
        wb += MG.words_count(base)
        wn += MG.words_count(chosen if chosen is not None else base)
    ok("слов на незацикленных страницах не убыло", wn >= wb, f"{wb} -> {wn}")

    # 5. Каждая ссылка на картинку разрешима.
    #    Мутация: снять охрану рисунков — появятся битые src.
    miss = [x for x in IMGSRC.findall(text)
            if not os.path.exists(os.path.join(d, x))]
    ok("ни одной битой ссылки на картинку", not miss,
       miss[0] if miss else "")

    # 6. У каждой таблицы либо вырезка, либо честная пометка о её отсутствии.
    #    Мутация: вернуть drop_lost_scans к `return md, 0` — ссылка на
    #    невыгруженную вырезку останется и будет вести в никуда.
    dangling = [x for x in MG.TBL_SCAN.findall(text)
                if not os.path.exists(os.path.join(d, x))]
    ok("ни одной ссылки на несуществующую вырезку", not dangling,
       dangling[0] if dangling else "")

    # 7. Свидетели не содержат выбранной страницы.
    #    Мутация: собрать свидетелей из книг проходов, как раньше — страница,
    #    взятая у прохода 2, начнёт сличаться сама с собой, и `≠` на ней не
    #    встанет никогда.
    ok("свидетелей ровно столько, сколько прочих проходов",
       len(wits) == len(passes) - 1, f"{len(wits)}")
    self_wit = 0
    for i in range(len(note["names"])):
        srcs = [w[i] for w in note["wit_src"] if w[i] is not None]
        if note["pick"][i] in srcs or len(set(srcs)) != len(passes) - 1:
            self_wit += 1
    ok("ни одна взятая у свидетеля страница не служит сама себе свидетелем",
       self_wit == 0, f"таких страниц {self_wit}")

print("\nне прошло проверок:", bad)
sys.exit(1 if bad else 0)
