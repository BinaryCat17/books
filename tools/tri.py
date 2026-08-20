"""Трёхстороннее сравнение: мы, Mistral и собственный текстовый слой PDF.

Ни один из трёх не эталон. Но там, где двое независимых согласны, а третий
расходится — почти наверняка ошибается третий. Это даёт оценку точности в
абсолютных величинах, а не относительно чьего-то разбора.
"""
import json, re, html, glob, sys, collections
import pypdfium2 as pdfium

tag = re.compile('<[^>]+>')
FIRST = 302


def words(t):
    t = html.unescape(tag.sub(' ', t))
    t = t.replace('’', "'").replace('”', '"').replace('“', '"')
    t = re.sub(r'[^A-Za-z0-9]+', ' ', t)
    return [w for w in t.lower().split() if w]


run = sys.argv[1]
pdf = pdfium.PdfDocument('bench/tables20.pdf')
ref = json.load(open('processed/book-mistral/raw.json'))['pages']
ours_f = sorted(glob.glob(f'{run}/pages/*.md'))

tot = collections.Counter()
for i in range(20):
    src = {
        'наш':     collections.Counter(words(open(ours_f[i]).read())),
        'mistral': collections.Counter(words(ref[FIRST + i]['markdown'])),
        'слой':    collections.Counter(words(pdf[i].get_textpage().get_text_range())),
    }
    keys = set().union(*src.values())
    for w in keys:
        have = [n for n, c in src.items() if c[w]]
        if len(have) >= 2:
            # берём минимальное согласованное число вхождений у двух источников
            cnt = sorted((src[n][w] for n in have), reverse=True)[1]
            tot['согласие'] += cnt
            for n in src:
                tot[f'есть:{n}'] += min(src[n][w], cnt)
        for n in have if len(have) == 1 else []:
            tot[f'только:{n}'] += src[n][w]

c = tot['согласие']
print(f'слов, где хотя бы двое согласны: {c}')
for n in ('наш', 'mistral', 'слой'):
    print(f'  {n:8} содержит {tot[f"есть:{n}"]:5} из них — {tot[f"есть:{n}"]/c:.1%}'
          f'   ; слов, которых нет ни у кого другого: {tot[f"только:{n}"]}')
