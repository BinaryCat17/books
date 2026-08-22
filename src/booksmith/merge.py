"""Свод нескольких проходов в одну книгу с пометками неустойчивости.

Основой берётся первый проход — жадный, лучший одиночный ответ.  Остальные
читались при ненулевой температуре и служат свидетелями: ячейка, прочитанная
всеми одинаково, надёжна; разошедшаяся — нет.

Пометки в итоге две, и они про разное:
  ⚠  модель сама не была уверена (по вероятностям токенов);
  ≠  чтения разошлись (модель гадала, но уверенно).
Первый признак ловит искажённый текст, второй — правдоподобную выдумку.
"""
import collections, difflib, glob, html, os, re, shutil, sys

TAG = re.compile(r"<[^>]+>")
CELL = re.compile(r"(<t[dh][^>]*>)(.*?)(</t[dh]>)", re.I | re.S)
TABLE = re.compile(r"<table\b.*?</table>", re.I | re.S)


def plain(c):
    return html.unescape(TAG.sub("", c)).replace("⚠", "").replace("≠", "").strip()


def cells_of(path):
    md = open(path, encoding="utf-8").read()
    out = collections.Counter()
    for t in TABLE.finditer(md):
        for _, body, _ in CELL.findall(t.group(0)):
            v = plain(body)
            if v:
                out[v] += 1
    return out


# Число целиком, вместе с ведущей точкой: в этой предметной области `.0005`
# пишут и так, и как `0.0005`, и без ведущей точки шаблон превращал одно
# написание в другое в мнимое расхождение — из 41 первой пометки таких было
# больше половины.  Хвостовая пунктуация в число не входит: `26.30,` — это
# число и запятая, а не число с запятой.
#
# Ведущая точка засчитывается, только если перед ней НЕ буква: иначе точка от
# «Sec.» прилипает к номеру раздела, и `Sec. 27.35` против `Sec.27.35`
# объявляется расхождением чисел, хотя различие в пробеле.
NUM = re.compile(r"(?<![^\W\d_])\.?\d+(?:[.,]\d+)*")
# Формулы LaTeX: внутрь них не заходим вовсе.  Замер на курсе физики: токены
# формул расходятся между чтениями на 38-40%, то есть почти всегда, а пометка
# внутри `$…$` вдобавок ломает саму формулу — `\sqrt{<mark>0.0049</mark>…}`
# перестаёт быть формулой.  Расхождения в математике надо ловить иначе, и это
# отдельная работа.
MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$", re.S)
PROSE_MARK = "чтения разошлись"


def _paragraphs(md):
    """Абзацы страницы без таблиц.

    Таблицы вырезаются целиком: их ячейки сличаются отдельно и точнее, по
    содержимому, а не по месту.
    """
    body = TABLE.sub(lambda m: "\x00", md)
    return re.split(r"(\n\s*\n)", body)


def _key(p):
    """Ключ абзаца для сопоставления: только буквы и цифры, без регистра."""
    return re.sub(r"[\W_]+", " ", TAG.sub(" ", p), flags=re.UNICODE).strip().casefold()


def _same_number(a, b):
    """Одно ли это число, записанное по-разному.

    `.001` и `0.001` — одно и то же; `.001` и `.0001` — разное.  Запятая и
    точка тоже одно: в русской книге распознаватель пишет разделитель то так,
    то этак, и без этой поправки на курсе физики семь пометок из двадцати были
    мнимыми — ровно смена написания.
    """
    def n(x):
        x = x.replace(",", ".")      # `0,5` и `0.5` — одно число
        return x.lstrip("0") if x[:2] == "0." else x
    return n(a) == n(b)


def _numbers(text):
    """Числа в тексте — со смещениями, минуя разметку.

    Внутрь тегов не заходим: в `<img src="...0091_1011...">` цифр больше, чем
    во всей странице, и все они к содержанию отношения не имеют.
    """
    holes = [(m.start(), m.end()) for m in TAG.finditer(text)]
    holes += [(m.start(), m.end()) for m in MATH.finditer(text)]
    out = []
    for m in NUM.finditer(text):
        if any(a <= m.start() < b for a, b in holes):
            continue
        # Числа, липнущие к знакам LaTeX, пропускаем даже вне `$…$`:
        # надстрочник `10^{14}` распадается у одного чтения в `1014`, у
        # другого в `10` и `14`, и свод объявляет расхождением развал
        # разметки, а не расхождение величины.
        near = text[max(0, m.start() - 1):m.start()] + text[m.end():m.end() + 1]
        if set(near) & set("^_{}\\"):
            continue
        val = m.group(0).rstrip(".,")
        out.append((m.start(), m.start() + len(val), val))
    return out


def mark_prose(base_md, witness_mds):
    """Пометить числа прозы, в которых чтения разошлись.

    Зачем это вообще: до сих пор свод сличал ТОЛЬКО ячейки таблиц, а проза
    первого прохода копировалась в итог побайтово.  Замер показал цену такой
    экономии — в справочнике по станкам 0.29% знаков книги лежит в ячейках, то
    есть проверялось три сотых доли текста, а в прозе оставались 69
    неподтверждённых чисел на сорока страницах: допуски вида `.001` против
    `.0001` и ссылки `Sec. 18.7` против `13.7`.  Ровно та правдоподобная
    выдумка, которую вероятности токенов не ловят по определению — модель в
    ней уверена.

    Сличаются ЧИСЛА, а не слова.  Пословное сличение годится для прозы
    справочника (0.29% помеченных слов, медиана ноль на страницу), но на книге
    с формулами превращается в шум: у Фейнмана расходится 6.9% слов, а токены
    LaTeX — на 38-40%.  Числа же дают 69 и 90 пометок на всю книгу
    соответственно, без шума вовсе, и это именно то, чего нельзя чинить на
    глаз.

    В подпись пометки кладутся варианты свидетелей.  Это улика, а не подсказка
    к исправлению: правило «числа только помечать, никогда не восстанавливать»
    остаётся, но человеку, идущему сверять со сканом, полезно знать, что
    прочли другие проходы.
    """
    base = _paragraphs(base_md)
    wits = [_paragraphs(w) for w in witness_mds]
    if not wits:
        return base_md, 0, 1

    # Абзацы сопоставляем, а не приравниваем по номеру.  Требование «одинаковое
    # число абзацев» оставляло несверенными 117 страниц из 539: проходы делят
    # текст по-разному (на стр. 0002 первый дал 35 абзацев, второй 19), и это
    # не разметка, а настоящее расхождение дробления.  Сличаем только те
    # абзацы, которые сошлись у ВСЕХ свидетелей однозначно; остальные считаем
    # несверенными и говорим об этом числом.
    def _pair(a, b):
        ka = [_key(x) for x in a]
        kb = [_key(x) for x in b]
        out = {}
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, ka, kb, autojunk=False).get_opcodes():
            # `equal` — якоря, `replace` равной длины — то, ради чего всё и
            # затевалось: абзацы соответствуют друг другу, но ОТЛИЧАЮТСЯ.
            #
            # Первая редакция брала только `equal`, и это была ошибка по
            # существу: сопоставление по равенству исключает ровно те абзацы,
            # где чтения разошлись.  Замер поймал сразу — пометок стало 2
            # вместо 30.
            if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
                for d in range(i2 - i1):
                    out[i1 + d] = j1 + d
        return out

    pairs = [_pair(base, w) for w in wits]
    aligned = set(pairs[0])
    for p in pairs[1:]:
        aligned &= set(p)

    marked = 0
    blind = 0
    out = list(base)
    for i, part in enumerate(base):
        if i % 2 or "\x00" in part or not part.strip():
            continue
        bn = _numbers(part)
        if not bn:
            # База чисел не видит, а свидетель видит — число пропало при
            # чтении.  Это ровно та потеря, которую иначе не заметить: искать
            # нечего, потому что искомого в тексте нет.
            if i in aligned and any(_numbers(w[p[i]])
                                    for w, p in zip(wits, pairs)):
                out[i] = part.rstrip() + " ≠"
                marked += 1
            continue
        if i not in aligned:
            # Абзац не сошёлся ни с одним свидетелем — числа в нём не
            # проверены никем, и это надо назвать, а не замолчать.
            blind += 1
            continue
        wn = [_numbers(w[p[i]]) for w, p in zip(wits, pairs)]
        if any(len(x) != len(bn) for x in wn):
            # Состав чисел разошёлся — метим абзац целиком, поштучно тут
            # сопоставлять уже нечем.
            # Видимая пометка, а не HTML-комментарий.  Первая редакция ставила
            # комментарий, и в нём тонули три четверти всех пометок: в html,
            # epub и pdf он не виден вовсе, а среди спрятанного были настоящие
            # расхождения цифр.  `≠` — тот же знак, что и в ячейках таблиц, и
            # он уже описан в work_instruction.md.
            out[i] = part.rstrip() + " ≠"
            marked += 1
            continue
        new = part
        decayed = False
        for k in range(len(bn) - 1, -1, -1):
            a, b, val = bn[k]
            alt = sorted({x[k][2] for x in wn
                          if not _same_number(x[k][2], val)})
            if not alt:
                continue
            # Развал разметки не выдаём за расхождение величины.  Надстрочник
            # `10^{14}` у одного чтения слипается в `1014`, у другого
            # рассыпается на `10` и `14`; называть это «прочли 1014 против 10»
            # значит врать читателю.  Признак: одно число — начало другого, и
            # длина разошлась больше чем на знак.  Абзац пометку всё равно
            # получит, но по составу чисел, а не поимённо.
            if all((val.startswith(x) or x.startswith(val))
                   and abs(len(val) - len(x)) >= 2 for x in alt):
                decayed = True
                continue
            new = (new[:a] + f'<mark title="{PROSE_MARK}: {", ".join(alt)}">'
                   + new[a:b] + "</mark>" + new[b:])
            marked += 1
        if decayed and new is part:
            new = part.rstrip() + " ≠"
            marked += 1
        out[i] = new

    if not marked:
        return base_md, 0, blind
    # Собираем обратно, вернув таблицы на место — по порядку, а не поиском
    # первого NUL: если такой символ попадётся в самом тексте, поиск подставит
    # таблицу в середину абзаца и оставит голый NUL на её месте.  Байт этот в
    # разборах не встречался ни разу, но тихая порча книги дороже одной строки.
    tables = iter(TABLE.findall(base_md))
    res = re.sub("\x00", lambda _: next(tables).replace("\\", "\\\\"),
                 "".join(out))
    return res, marked, blind


def merge(dirs, dst):
    base, others = dirs[0], dirs[1:]
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(base, dst)
    pages = sorted(glob.glob(os.path.join(dst, "pages", "*.md")))
    marked = total = 0
    prose_marked = prose_blind = missing = 0
    for f in pages:
        stem = os.path.basename(f)
        paths = [os.path.join(o, "pages", stem) for o in others]
        # Нехватку страницы у свидетеля считаем и называем.  Прежде она уходила
        # через `except FileNotFoundError: continue`, и страница выглядела
        # проверенной, хотя не проверялась вовсе: на опыте с усечённым
        # свидетелем 130 страниц прошли без единой пометки там, где при целом
        # свидетеле их стояло 47.  Хуже того, перехват накрывал ВЕСЬ список
        # свидетелей — нехватка у одного отменяла проверку по остальным.
        have = [p for p in paths if os.path.exists(p)]
        if len(have) < len(paths):
            # Считаем неполные страницы, но проверку по уцелевшим свидетелям НЕ
            # отменяем.  Прежний `except FileNotFoundError: continue` накрывал
            # весь список: нехватка у одного отменяла сверку по всем, и
            # страница выглядела проверенной, не будучи ею.
            missing += 1
            if not have:
                continue
        paths = have
        src = open(f, encoding="utf-8").read()
        changed = False

        # Проза — на каждой странице, а не только там, где есть таблица.
        # Прежде страница без таблицы даже не читалась.
        src, pm, pb = mark_prose(src, [open(p, encoding="utf-8").read()
                                       for p in paths])
        prose_marked += pm
        prose_blind += pb
        changed = changed or bool(pm)

        if "<table" not in src.lower():
            if changed:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(src)
            continue
        witness = [cells_of(p) for p in paths]
        seen = collections.Counter()

        def one(m):
            nonlocal marked, total
            v = plain(m.group(2))
            if not v:
                return m.group(0)
            total += 1
            seen[v] += 1
            k = seen[v]
            if all(w[v] >= k for w in witness):
                return m.group(0)          # подтверждена обоими свидетелями
            marked += 1
            return m.group(1) + m.group(2) + " ≠" + m.group(3)

        out = []
        prev = 0
        for t in TABLE.finditer(src):
            out.append(src[prev:t.start()])
            out.append(CELL.sub(one, t.group(0)))
            prev = t.end()
        out.append(src[prev:])
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("".join(out))

    # Книжный файл размечаем на месте, а не пересобираем из страниц: в нём
    # склеены таблицы, разорванные разрывом страницы, и пересборка это
    # теряла.  Счётчики здесь по всей книге, а не по странице — границ
    # страниц в нём уже нет.  Огрубление безопасное: оно может лишь не
    # заметить расхождение, но не выдумать его.
    book = os.path.join(dst, "book", "book.md")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    if os.path.exists(book):
        whole = [collections.Counter() for _ in others]
        for o, acc in zip(others, whole):
            bf = os.path.join(o, "book", "book.md")
            if os.path.exists(bf):
                acc.update(cells_of(bf))
            else:
                for f in sorted(glob.glob(os.path.join(o, "pages", "*.md"))):
                    acc.update(cells_of(f))
        src = open(book, encoding="utf-8").read()
        # Проза книжного файла размечается отдельно: `book.md` собирается
        # склейкой страниц с починкой таблиц через разрыв, и постраничные
        # пометки в него не переносятся.  А читают именно его — CLAUDE.md
        # называет его единственным готовым текстом.
        wb = [os.path.join(o, "book", "book.md") for o in others]
        wb = [x for x in wb if os.path.exists(x)]
        if wb:
            src, bp, _ = mark_prose(src, [open(x, encoding="utf-8").read()
                                          for x in wb])
            if bp:
                print(f"в книжном файле помечено чисел прозы: {bp}")
        seen = collections.Counter()

        def book_cell(m):
            v = plain(m.group(2))
            if not v:
                return m.group(0)
            seen[v] += 1
            k = seen[v]
            if all(w[v] >= k for w in whole):
                return m.group(0)
            return m.group(1) + m.group(2) + " ≠" + m.group(3)

        out = []
        prev = 0
        for t in TABLE.finditer(src):
            out.append(src[prev:t.start()])
            out.append(CELL.sub(book_cell, t.group(0)))
            prev = t.end()
        out.append(src[prev:])
        with open(book, "w", encoding="utf-8") as fh:
            fh.write("".join(out))
    else:
        with open(book, "w", encoding="utf-8") as out:
            for f in pages:
                out.write(open(f, encoding="utf-8").read())
                out.write("\n\n")
    # Число свидетелей — первое, что надо знать про пометки: при одном
    # проходе ноль пометок значит «никто не сверял», а читается как «все
    # чтения сошлись».  Разница между этими двумя ровно та, ради которой
    # многопроходность и заведена.
    if not others:
        print("ВНИМАНИЕ: свидетелей нет — сверять было не с чем. "
              "Отсутствие пометок ≠ здесь не значит, что чтения сошлись.")
    else:
        print(f"свидетелей: {len(others)}")
    print(f"ячеек в таблицах {total}, помечено неустойчивыми {marked} "
          f"({marked/max(total,1):.0%})")
    print(f"чисел в прозе помечено {prose_marked}; абзацев с числами, не "
          f"сошедшихся ни с одним свидетелем и потому не сверенных: "
          f"{prose_blind}")
    if missing:
        # Число, а не молчание: страница без свидетеля НЕ проверена, и это
        # надо видеть, а не выводить из тишины.
        print(f"ВНИМАНИЕ: у свидетелей не хватает {missing} страниц — "
              f"они не сверены ничем")
    print(f"книга собрана: {book}")



