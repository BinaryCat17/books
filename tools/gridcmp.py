"""Попадают ли значения в свой столбец — то, что важно для пересказа.

Ячейку читателю-человеку подсказывает вёрстка, а модели-пересказчику —
только разметка.  Поэтому сверяется не число ячеек, а строки значений:
та же тройка чисел в том же порядке.
"""
import json, re, html, glob, sys, collections

tag = re.compile('<[^>]+>')
FIRST = 302
VAL = re.compile(r'\.\d{3,5}|\d+/\d+')


def norm(c):
    c = html.unescape(tag.sub('', c)).strip()
    return re.sub(r'\s+', '', c.replace('”', '"').replace('’', '"')
                  .replace("'", '"'))


def rows_html(md):
    out = []
    for t in re.finditer(r'<table\b.*?</table>', md, re.I | re.S):
        tb = []
        for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t.group(0), re.I | re.S):
            tb.append([norm(c) for c in
                       re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.I | re.S)])
        out.append(tb)
    return out


def rows_md(md):
    out, cur = [], []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith('|') and s.endswith('|'):
            if not re.fullmatch(r'\|[\s:|-]+\|', s):
                cur.append([norm(c) for c in s.strip('|').split('|')])
        elif cur:
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out


def valrows(tb):
    """Строки, состоящие только из значений — их и надо сверять."""
    out = []
    for r in tb:
        v = [c for c in r if c]
        if len(v) >= 2 and sum(1 for c in v if VAL.search(c)) >= 2:
            out.append(tuple(v))
    return out


run = sys.argv[1]
ref = json.load(open('processed/book-mistral/raw.json'))['pages']
idx = (json.load(open(os.environ['TABCMP_PAGES']))
       if (os := __import__('os')).environ.get('TABCMP_PAGES')
       else list(range(FIRST, FIRST + 20)))
files = sorted(glob.glob(f'{run}/pages/*.md'))
tot = hit = 0
for i, pg in enumerate(idx):
    want = [v for tb in rows_md(ref[pg]['markdown']) for v in valrows(tb)]
    md = open(files[i]).read()
    got = [v for tb in rows_html(md) + rows_md(md) for v in valrows(tb)]
    pool = collections.Counter(got)
    for v in want:
        tot += 1
        if pool[v]:
            pool[v] -= 1; hit += 1
        else:
            print(f'  стр {pg}: строка значений {v} не воспроизведена; '
                  f'у нас рядом {[g for g in got if len(g)==len(v)][:2]}')
print(f'\n{run}: строк значений в эталоне {tot}, воспроизведено точно {hit} '
      f'({hit/max(tot,1):.0%})')
