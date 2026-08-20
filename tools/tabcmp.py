"""Сравнение табличной части разбора с эталоном Mistral, постранично.

Сумма ячеек — плохая мера: перебор в ней считается как попадание. Поэтому
здесь на каждой странице печатаются обе величины рядом, а итог сводится не
только к сумме, но и к числу страниц, где мы попали в эталон.

    python tools/tabcmp.py bench/tables-mv3 [bench/olmocr ...]
"""
import json, re, sys, os

REF = "processed/book-mistral/raw.json"
FIRST, N = 302, 20  # bench/tables20.pdf — это страницы 302..321 книги


def cells(md: str) -> tuple[int, int]:
    """(таблиц, непустых ячеек) в тексте Markdown."""
    tabs = 0, 0
    n_t = n_c = 0
    rows = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            rows.append(s)
            continue
        n_t, n_c = _flush(rows, n_t, n_c)
        rows = []
    n_t, n_c = _flush(rows, n_t, n_c)
    # HTML-таблицы (PaddleOCR отдаёт их именно так)
    n_t += len(re.findall(r"<table", md, re.I))
    n_c += len([c for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", md, re.I | re.S)
                if c.strip()])
    return n_t, n_c


def _flush(rows, n_t, n_c):
    if len(rows) < 2:
        return n_t, n_c
    body = [r for r in rows if not re.fullmatch(r"\|[\s:|-]+\|", r)]
    if len(body) == len(rows):      # нет строки-разделителя — не таблица
        return n_t, n_c
    for r in body:
        n_c += len([c for c in r.strip("|").split("|") if c.strip()])
    return n_t + 1, n_c


def read_run(d: str) -> list[str]:
    pages = sorted(f for f in os.listdir(f"{d}/pages") if f.endswith(".md"))
    return [open(f"{d}/pages/{f}").read() for f in pages]


ref = json.load(open(REF))["pages"][FIRST:FIRST + N]
ref = [cells(p["markdown"]) for p in ref]

runs = sys.argv[1:]
data = {}
for d in runs:
    try:
        data[d] = [cells(m) for m in read_run(d)]
    except Exception as exc:
        print(f"{d}: пропуск ({exc})")

name = lambda d: os.path.basename(d)[:11]
print("стр |  эталон  | " + " | ".join(f"{name(d):>10}" for d in data))
tot = {d: [0, 0] for d in data}
tref = [0, 0]
for i in range(N):
    rt, rc = ref[i]
    tref[0] += rt; tref[1] += rc
    row = f"{FIRST+i:4}| {rt:2}т {rc:3}я | "
    for d in data:
        t, c = data[d][i] if i < len(data[d]) else (0, 0)
        tot[d][0] += t; tot[d][1] += c
        mark = " " if (t, c) == (rt, rc) else ("!" if c > rc else "-")
        row += f"{t:2}т {c:3}я{mark}| "
    print(row)
print("итог| " + f"{tref[0]:2}т {tref[1]:3}я | " +
      " | ".join(f"{tot[d][0]:2}т {tot[d][1]:3}я " for d in data))
for d in data:
    hit = sum(1 for i in range(min(N, len(data[d]))) if data[d][i] == ref[i])
    print(f"{name(d)}: страниц точно как в эталоне {hit}/{N}")
