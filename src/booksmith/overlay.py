"""`books overlay` -- look with your eyes at what the number measured.

A bench that checks itself by numbers and that nobody has seen is not an
instrument. In one session this bench lied with boxes six times and the number
never looked ill: empty text boxes, half a spread off the sheet, a "drawing" of
forty-seven parallel lines, a formula box wider than its formula, a line for a
paragraph, one box over a running head of two. All six show on the sheet, none
in the report.

WE SHOW DIVERGENCES, NOT EVERYTHING. The first edition drew both markups whole:
on a page where the model is right, two hundred nearly coincident rectangles
with two captions over each -- the sheet stopped being readable exactly where
there was nothing to read. Now a matched pair is one thin grey box without a
caption, and only the divergence is shouted: what the model missed and what it
found that is not there.

THERE IS NO LEGEND. In a corner it lay over the first blocks of the page; on a
sheet of its own it is one more sheet nobody looks at. The colours below speak
for themselves, and a caption stands only where there is something to say.

DASHES ARE GIVEN AS A STRING, not a tuple. The first edition passed
`dashes=(0, 3)`; pymupdf wants `"[3 3] 0"` and silently drew SOLID -- both
markups looked identical, and nothing whatever told them apart.
"""
import json
import os

import pymupdf

# Caption font: the built-in `helv` knows no Cyrillic and drew captions as
# emptiness -- which of the two markups a box came from was unreadable.
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

MATCHED = (0.55, 0.55, 0.55)      # grey and thin: nothing to look at here
NOT_FOUND = (0.85, 0.10, 0.10)     # red: in truth, absent from the model
SPURIOUS = (0.95, 0.55, 0.00)       # orange: in the model, absent from truth
ONE = (0.15, 0.35, 0.85)         # blue: one markup, nothing to compare with
# A DIVERGENT LABEL is not "a spurious box" and has its own colour now. The
# caption «ярлык: A -> B» took the same orange as «ЛИШНЯЯ» and hung over a GREY
# box: its colour contradicted its own box, and the reader hunted an orange
# rectangle that was not there. On `bench/slovar` 207 of 517 pairs (40%) carry
# it, on one sheet 56 of 56; by eye a caption is 1.47 times wider than its box,
# 61 of 62 are covered by another, and a real «ЛИШНЯЯ» beside them goes
# invisible. Narrow -- 10 or more captions on 5 sheets of 859, all slovar -- but
# colour cures it, patience does not.
LABEL = (0.45, 0.25, 0.65)        # purple: same box, different name


class OverlayError(RuntimeError):
    pass


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_book(pdf: str, marks) -> str:
    """Is the markup about this PDF. Unchecked, a foreign truth lies down
    silently and looks like the model's trouble -- it is the directory's."""
    mine = _sha256(pdf)
    said, unchecked = [], []
    for d, tag in marks:
        was = len(said)
        up = os.path.dirname(d.rstrip("/"))
        for name, path_in in (("manifest.json", ("sha256 pdf",)),
                              ("run.json", ("source", "sha256"))):
            path = os.path.join(up, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                j = json.load(f)
            for k in path_in:
                j = (j or {}).get(k) if isinstance(j, dict) else None
            if not j:
                continue
            if j != mine:
                raise OverlayError(
                    f"разметка «{tag}» ({d}) про ДРУГУЮ книгу: в её слепке "
                    f"sha256 {j[:12]}, а у {pdf} — {mine[:12]}. Нарисованные "
                    f"рамки выглядели бы дефектом модели.")
            if tag not in said:
                # ONCE PER MARKUP, not per snapshot found. `said.append` used to
                # sit inside the loop over the two files, and with both
                # `manifest.json` and `run.json` in one directory the line came
                # out «sha256 сверен для И, М, М».
                said.append(tag)
        if len(said) == was:
            unchecked.append(tag)
    # WHAT WAS NOT CHECKED IS NAMED ALOUD. It used to print «sha256 сверен для
    # И» and say not a word about «М» being unchecked: half a guard read as the
    # whole guard. The same zero from not understanding -- "we did not look"
    # dressed as "it matched".
    ok = f"sha256 сверен для {', '.join(said)}" if said else None
    no = (f"НЕ СВЕРЕН для {', '.join(unchecked)}: слепка рядом нет, про ту "
          f"ли книгу эта разметка — сказать нечем") if unchecked else None
    return "; ".join(x for x in (ok, no) if x) or "sha256 сверять нечем"


def _pages(d: str) -> dict:
    if not os.path.isdir(d):
        raise OverlayError(f"нет каталога разметки {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name == "run.json":
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if "blocks" not in p or "index" not in p:
            raise OverlayError(f"{name}: не похоже на страницу разметки")
        out[int(p["index"])] = p
    if not out:
        raise OverlayError(f"в {d} нет ни одной страницы разметки")
    return out


def _pair(truth, model):
    """Match one page's boxes: (pairs, truth left over, model left over). The
    match is what `books score` measures by, or sheet and number say different
    things.

    ARTEFACT IS MATCHED WITH ARTEFACT. `books score` looks for a truth artefact
    only among the model's ARTEFACT boxes (pass A); its label-blind pass serves
    reading order and text, not the final share. Blind matching drew a table
    covered by a `text` box in thin grey «совпало», counted it matched and kept
    the page out of the divergences -- where the number called it lost: 51
    artefacts over nine benches (33 annopage, 14 hard, 2 matematika, one each
    atlas and hard36), 31 of them tables eaten by a text box (table->text 17,
    table->content 13, table->reference 1).

    The side comes from the same `label in arte` as in `compare_pages`, not from
    `policy.role`: a label the policy does not describe must behave here as it
    does in score, or sheet and number diverge again, now on the exception.
    """
    from .metrics import _pick, _area
    from . import policy
    arte = set(policy.artefacts())
    pairs, lost, extra = [], [], []
    for side in (True, False):
        t = [b for b in truth if (b["label"] in arte) == side]
        m = [x for x in model if (x["label"] in arte) == side]
        # The greed order comes from the same side of `books score`: artefacts
        # in markup order as in pass A, the rest largest first as in pass B. One
        # rule with another order would part the pairs on contested places.
        if not side:
            t = sorted(t, key=lambda z: -_area(z["box"]))
        used = set()
        for b in t:
            j = _pick(b, m, used)
            if j is None:
                lost.append(b)
                continue
            used.add(j)
            pairs.append((b, m[j]))
        extra += [x for j, x in enumerate(m) if j not in used]
    return pairs, lost, extra


def _rect(page, box, k, color, width, dashes=None):
    page.draw_rect(pymupdf.Rect(box[0] * k, box[1] * k, box[2] * k, box[3] * k),
                   color=color, width=width, dashes=dashes)


def _label(page, box, k, color, text, above=True):
    x, y = box[0] * k + 1, box[1] * k - 2
    if not above:
        y = box[3] * k + 7
    page.insert_text((x, max(7.0, y)), text, fontname="L", fontsize=6.0,
                     color=color)


def build(pdf: str, out: str, marks: list[tuple[str, str]], only=None,
          log=print) -> dict:
    """Lay markup over the PDF pages, SHOWING THE DIVERGENCES.

    `marks` is a list of (directory, tag). Two markups are compared; a single
    one is drawn whole, because there is nothing to compare it with.

    WHAT TRUTH DOES NOT MARK UP IS NOT "SPURIOUS". Truth declares that itself,
    by the meta field `text_marked`; no field means it does mark up. Boxes of
    unmarked classes are drawn as a blue hairline without a caption and go into
    a quantity of their own, not into "spurious".

    THIS IS SAID ALWAYS, not only when such boxes turn up. "Outside the markup
    0" has two kinds: truth marks text up and nothing is extra -- and truth
    marks no text while the model produced none. Silence passes the second for
    the first, a zero from not understanding for a zero from a check.
    """
    from . import policy

    def role(label: str) -> str:
        # A label unknown to the policy is not hidden: let it stay loud.
        try:
            return policy.role(label)
        except policy.UnknownLabel:
            return "artifact"

    def die(msg: str):
        """Close the document and fail with OUR message.

        The message is built at the call site, BEFORE the document is closed.
        Guards used to `doc.close()` a line above `raise OverlayError(...
        doc.page_count ...)`, and pymupdf 1.28.2 throws on a closed document --
        `page_count` a ValueError "document closed", `page.rotation` an
        AssertionError "page is None". That flew out instead of the explanation,
        and as a bare stack trace: `overlay.build` is wrapped in nothing in
        cli.py. Checked on all four guards that read after closing.
        """
        doc.close()
        raise OverlayError(msg)

    note = _same_book(pdf, marks)
    sets = [(_pages(d), tag) for d, tag in marks]
    doc = pymupdf.open(pdf)
    if not os.path.exists(FONT):
        die(f"нет шрифта {FONT}: подписи выйдут пустыми")
    if only is not None:
        bad = [i for i in only if not 0 <= i < doc.page_count]
        if bad:
            die(f"в {pdf} нет страниц {bad}: всего {doc.page_count}")
    for pages, tag in sets:
        lost = sorted(i for i in pages if not 0 <= i < doc.page_count)
        if lost:
            die(f"у разметки «{tag}» есть страницы {lost[:5]}, которых нет в "
                f"{pdf} ({doc.page_count} страниц): они исчезли бы без счёта.")

    counts = {"matched": 0, "missed": 0, "spurious": 0, "outside_markup": 0,
              "pages_without_text_markup": 0, "pages_compared": 0,
              # MISSES ARE COUNTED BY NAME. A page absent from one markup used
              # to be skipped by both `continue` branches in silence, and the
              # sheet looked complete. Measured: drop 3 pages of 13 from the
              # model on slovar and «НЕ НАШЛА 6» does not flinch while
              # divergences get FEWER (10 -> 7) -- the model improved by losing
              # part of its answer. `books score` on that input refuses to count
              # aloud: «модель не разметила страницы [0, 5, 11]: сверять нечего».
              "missing_in_truth": [], "missing_in_model": [], "in_neither": 0,
              "pages": []}
    # TWO QUANTITIES, and there used to be one. `drawn` counts BOXES (in every
    # branch, and the "not one landed" guard stands on it); `sheets` counts the
    # SHEETS reached. The summary printed `doc.page_count`, a third quantity:
    # `--pages 102` on the golden bench gave «листов 600» with one drawn. Three
    # things under one word is the trouble of «глав 0» standing for "I did not
    # recognise them".
    drawn = 0
    sheets = 0
    for i, page in enumerate(doc):
        if only is not None and i not in only:
            continue
        if page.rotation:
            die(f"страница {i} повёрнута атрибутом PDF ({page.rotation}°): "
                f"рамки лягут поперёк. Разверни PDF до наложения.")
        page.insert_font(fontname="L", fontfile=FONT)
        p0 = sets[0][0].get(i)
        if p0 is None:
            # Missing from the FIRST markup. Missing from the second too, it is
            # a sheet nobody marked up (ordinary with a partial `books detect`).
            # Present in the second, it is a hole in the first, and silence
            # about that is not allowed.
            if len(sets) > 1 and sets[1][0].get(i) is not None:
                counts["missing_in_truth"].append(i)
            else:
                counts["in_neither"] += 1
            continue
        k = page.rect.width / p0["width"]
        kh = page.rect.height / p0["height"]
        if abs(k - kh) > 1e-3:
            die(f"страница {i}: растр разметки {p0['width']}x{p0['height']} "
                f"не той пропорции, что лист — рамки лягут растянутыми.")
        if len(sets) == 1:
            for b in p0["blocks"]:
                _rect(page, b["box"], k, ONE, 1.1)
                _label(page, b["box"], k, ONE, f"{b['label']}")
                drawn += 1
            sheets += 1
            continue
        p1 = sets[1][0].get(i)
        if p1 is None:
            counts["missing_in_model"].append(i)
            continue
        # EACH MARKUP HAS ITS OWN SCALE. The first one's coefficient used to be
        # taken and applied to the second in silence: if the model's output
        # raster differs from truth's by even a pixel, the boxes lie shifted and
        # the sheet looks convincing.
        if (p1["width"], p1["height"]) != (p0["width"], p0["height"]):
            die(f"страница {i}: растр истины {p0['width']}x{p0['height']}, "
                f"растр модели {p1['width']}x{p1['height']} — рамки лягут "
                f"в разных системах координат.")
        sheets += 1
        pairs, lost, extra = _pair(p0["blocks"], p1["blocks"])
        # The sign comes from TRUTH and is per page; no field means it marks up.
        # Per page is not pedantry: on the hard36 bench text is marked on one
        # page of thirty-six, and a sign "for the whole bench" would lie about
        # both halves at once.
        marked = bool((p0.get("meta") or {}).get("text_marked", True))
        counts["pages_compared"] += 1
        counts["pages_without_text_markup"] += 0 if marked else 1
        # WE SHOUT ONLY AT WHAT THE NUMBER ALSO CALLS SPURIOUS. The sign used to
        # be one -- is the label an artefact -- and the sheet shouted orange at
        # everything: 508 boxes on the golden bench, of which `books score`
        # itself calls 110 spurious and DELIBERATELY forgives 350 (69%) as «на
        # объекте вне замера». Truth put those objects beyond the scored
        # boundary; blaming the model for a find there punishes it for a line WE
        # drew, and a person sentenced the model by a number the instrument
        # beside it refutes.
        #
        # The rule comes from `metrics.extra_kind` -- ONE for sheet and number,
        # not a second copy: copies drifting apart has already cost this project
        # thirteen names of seventeen.
        #
        # The `out_of_scope` field had NEVER been read here, though it lies
        # right beside: non-empty on 288 golden-bench pages of 600, 904 objects.
        from .metrics import extra_kind
        from . import policy as _pol
        _arte = set(_pol.artefacts())
        tb = [b for b in p0["blocks"] if b["label"] in _arte]
        paired = [b["box"] for b, _ in pairs if b["label"] in _arte]
        unpaired = [b["box"] for b in lost if b["label"] in _arte]
        outside = [o["box"] for o in
                   ((p0.get("meta") or {}).get("out_of_scope") or [])]
        loud, quiet = [], []
        for x in extra:
            if x["label"] in _arte:
                # `marked` plays no part here: it is about TEXT markup, and an
                # artefact is always marked. The old disjunction made it dead
                # the other way -- on the golden bench `text_marked` is false on
                # 600 pages of 600, so the second term always decided.
                kind = extra_kind(x["box"], paired, unpaired, outside, tb)
                x = dict(x, _trouble=kind)
                (loud if kind == "spurious_box" else quiet).append(x)
            else:
                (loud if marked else quiet).append(x)
        counts["matched"] += len(pairs)
        counts["missed"] += len(lost)
        counts["spurious"] += len(loud)
        counts["outside_markup"] += len(quiet)
        if lost or loud:
            counts["pages"].append(i)
        for b, x in pairs:
            # A matched pair is drawn as ONE thin box with no caption: two
            # nearly coincident boxes with two captions over each are what made
            # the sheet unreadable. The label, where it diverged, is the only
            # thing worth saying here.
            _rect(page, x["box"], k, MATCHED, 0.7)
            if b["label"] != x["label"]:
                _label(page, x["box"], k, LABEL,
                       f"ярлык: {b['label']} -> {x['label']}")
            drawn += 1
        for b in lost:
            _rect(page, b["box"], k, NOT_FOUND, 1.6)
            _label(page, b["box"], k, NOT_FOUND, f"НЕ НАШЛА  {b['label']}")
            drawn += 1
        for x in quiet:
            # Not drawing these at all is not an option: the sheet would say
            # nothing about the model having found anything -- a zero from not
            # understanding, passed off as a clean page.
            _rect(page, x["box"], k, ONE, 0.5, dashes="[1 2] 0")
            drawn += 1
        for x in loud:
            _rect(page, x["box"], k, SPURIOUS, 1.6, dashes="[3 3] 0")
            s = f" {x['score']:.2f}" if x.get("score") is not None else ""
            _label(page, x["box"], k, SPURIOUS, f"ЛИШНЯЯ  {x['label']}{s}",
                   above=False)
            drawn += 1

    if not drawn:
        die(f"ни одна страница разметки не легла на {pdf}: в PDF "
            f"{doc.page_count} страниц, а индексы разметки другие")
    n = doc.page_count
    # THE OUTPUT CARRIES ONLY WHAT WAS ASKED FOR. The whole document used to be
    # saved: `--pages 102` on the golden bench gave a 494 MB file, 417 KB LARGER
    # than the source, and the default `--out` put those 494 MB into
    # `bench/annopage/`. `only` governed the drawing loop alone. Measured:
    # `doc.select([102])` gives 658 KB in 0.1 s -- 751 times smaller, 50 times
    # faster.
    #
    # THE NUMBERING SHIFTS BY THIS, said aloud: in the output file the requested
    # sheets run consecutively from the first. A silent renumbering in an
    # instrument meant for the eye is the `--pages` off-by-one from the other
    # side.
    picked = None
    if only is not None and len(only) < n:
        picked = sorted(only)
        doc.select(picked)
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    log(note)
    log(f"{out}: листов нарисовано {sheets} из {n} в книге, рамок {drawn}")
    if picked:
        log(f"  в файл вошли только запрошенные листы, и НУМЕРАЦИЯ В НЁМ "
            f"СВОЯ: лист 1 выхода — это страница {picked[0] + 1} книги"
            + (f", последний — {picked[-1] + 1}" if len(picked) > 1 else ""))
    if len(sets) == 1:
        # NOTHING TO COMPARE WITH -- and that is not «совпало 0, НЕ НАШЛА 0,
        # ЛИШНИХ 0», which is what it used to print with boxes drawn: three
        # zeros and "divergences on 0 pages" read as "everything agreed" though
        # no comparison happened. A zero from not understanding, in the summary
        # line.
        log(f"  одна разметка «{sets[0][1]}»: сличать эти {drawn} рамок НЕ "
            f"С ЧЕМ. Это не «расхождений нет» — второй разметки не подали "
            f"вовсе")
    else:
        log(f"  совпало {counts['matched']}, "
            f"НЕ НАШЛА {counts['missed']}, ЛИШНИХ {counts['spurious']}; "
            f"расхождения на {len(counts['pages'])} страницах")
    # Misses as a quantity and by name, or an incomplete model output looks
    # like a clean sheet.
    for who, key in (("истины", "missing_in_truth"), ("модели", "missing_in_model")):
        if counts[key]:
            p = counts[key]
            log(f"  У {who} НЕТ {len(p)} страниц, которые есть у другой "
                f"разметки: {p[:8]}{' …' if len(p) > 8 else ''}. Эти листы "
                f"НЕ сличались, и их рамки в числа выше не вошли — сравнивать "
                f"лист с числом здесь нельзя")
    # A quantity rather than silence: «ЛИШНИХ 508» without this line would read
    # as "the whole sheet was checked", though text on these pages was not
    # checked at all.
    if counts["pages_without_text_markup"]:
        log(f"  текста истина НЕ размечает на "
            f"{counts['pages_without_text_markup']} страницах из "
            f"{counts['pages_compared']} (meta «текст размечен»: false): "
            f"{counts['outside_markup']} рамок модели этих разрядов "
            f"нарисованы волоском и в «лишних» НЕ считаны — это не ноль "
            f"лишних, это «сверять было нечем»")
    return counts
