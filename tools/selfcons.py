"""Самосогласованность: что модель читает одинаково при трёх попытках.

Вероятности токенов ловят искажённый текст, но не ловят правдоподобную
выдумку — она по определению высоковероятна.  Здесь проверяется другой
признак: если на неразборчивом месте модель гадает, при ненулевой температуре
она угадает по-разному.
"""
import re, html, glob, sys, collections

tag = re.compile('<[^>]+>')


def cells(path):
    """(страница, номер таблицы, номер ячейки) -> текст."""
    out = {}
    for f in sorted(glob.glob(f'{path}/pages/*.md')):
        pg = int(f[-7:-3])
        md = open(f).read()
        for ti, t in enumerate(re.finditer(r'<table\b.*?</table>', md, re.I | re.S)):
            k = 0
            for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t.group(0), re.I | re.S):
                for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.I | re.S):
                    txt = html.unescape(tag.sub('', c)).strip().replace('⚠', '').strip()
                    out[(pg, ti, k)] = txt
                    k += 1
    return out


runs = [cells(p) for p in sys.argv[1:]]
keys = set(runs[0])
for r in runs[1:]:
    keys &= set(r)
same = diff = 0
shown = 0
NUM = re.compile(r'\.\d{3,5}')
numdiff = 0
for k in sorted(keys):
    vals = {r[k] for r in runs}
    if len(vals) == 1:
        same += 1
    else:
        diff += 1
        if any(NUM.search(v) for v in vals):
            numdiff += 1
            if shown < 12:
                shown += 1
                print(f'  стр {302+k[0]} табл {k[1]} ячейка {k[2]}: {sorted(vals)}')
print(f'\nобщих ячеек {len(keys)}: совпали во всех трёх {same}, разошлись {diff} '
      f'(из них с числами {numdiff})')
print('расхождение по ячейкам:', f'{diff/max(len(keys),1):.1%}')
