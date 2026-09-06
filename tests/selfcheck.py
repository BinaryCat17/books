"""Mutation battery: a check must be able to fail.

The project rule about metrics -- feed it a broken input, make sure the number
falls -- holds for checks too. A green check on broken code is worse than a
missing one: the missing one is honestly silent, this one says "agreed" daily.

Each mutation BREAKS the guarded place -- a function swapped in memory, or a
COPY of the source with one line changed -- and names the checks that must go
red. The working tree is never touched: hand-editing files while seven agents
work beside you overwrites someone's edit.

Printed as quantities: mutations caught, missed, and WHICH checks no mutation
covers. An uncovered check is no disaster, but it must be known by number.
"""
import base64
import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import support                                              # noqa: E402
from booksmith import metrics, otsl, policy                 # noqa: E402
from booksmith import fitness as fit                        # noqa: E402
from booksmith.remote import vast as vastmod
from booksmith import order
from booksmith import annopage                              # noqa: E402
from booksmith import overlay                               # noqa: E402
from booksmith import djvu                                  # noqa: E402
from booksmith.doc import apply as ap                       # noqa: E402
from booksmith.doc import crop                              # noqa: E402
from booksmith.doc import feed                              # noqa: E402
from booksmith.doc import html as dhtml                     # noqa: E402
from booksmith.doc import swap                              # noqa: E402
from booksmith.models import base as mbase                  # noqa: E402
from booksmith.models import docling_heron as dh            # noqa: E402
from booksmith.run import knobs, replay, stamp              # noqa: E402
from booksmith.models import doclayout                      # noqa: E402
from booksmith import text as booktext                      # noqa: E402
from booksmith.read import Reader, Route, Said              # noqa: E402
from booksmith.read import http as vhttp                    # noqa: E402
from booksmith.read import run as vrun                      # noqa: E402
from booksmith.models.paddleocr_vl.reader import PaddleOcrVl  # noqa: E402
from booksmith import cyr as cyrmod                        # noqa: E402
from booksmith import schema                               # noqa: E402
from booksmith import acceptance                           # noqa: E402


# --- what we break with ----------------------------------------------------

@contextmanager
def attrs(obj, **kw):
    """Swap object fields for the duration of a mutation, then restore."""
    old = {k: getattr(obj, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(obj, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


COPY = ("models/doclayout.py", "models/docling_heron.py",
        "models/yolox_layout.py",
        # Entry point for the rented card: a copy of the `--pages` parser,
        # guarded by `test_parse_pages`, which reads the file FROM HERE via
        # `support.src_path`. Forget this line and the check reads the real
        # file past the damage -- green on broken code.
        "models/dots_ocr/entrypoint.py",
        # Contour ruler: `test_order` parses its `_by_reading` and demands the
        # assembly rule be asked of `order.py`, not repeated here.
        "metrics.py",
        # Script that ships to the rented card: `test_knobs` compares its
        # `${NAME:-default}` against the knob registry.
        "models/paddleocr_vl/run.sh",
        # Book builder: `test_html_order` parses its `build` and demands the
        # order check be present, not derived from the walk itself.
        "doc/html.py",
        # Table parsing: `test_otsl_html` demands ONE tag walk for two
        # consumers. A second walk would drift from the first silently.
        "otsl.py",
        # Replacement in the book: `test_torn` demands `from_read` ask the
        # sidecar and pass the truncation flag into the wrapper. This half has
        # already fallen off silently -- the mark was lost by exactly those
        # blocks that reached the reader as markup.
        "doc/apply.py")


@contextmanager
def sources(rel, old, new):
    """A copy of the source tree with one line changed.

    A copy: checks that read the source must go red on damage, and the working
    tree may not be damaged to make that happen.
    """
    tmp = tempfile.mkdtemp(prefix="booksmith-selfcheck-")
    try:
        for r in COPY:
            dst = os.path.join(tmp, r)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(support.src_path(r), dst)
        path = os.path.join(tmp, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if old not in text:
            raise AssertionError(
                f"мутация не наложилась: в {rel} нет строки {old!r} — "
                f"проверяемое место переписали, а батарея этого не знает")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        with attrs(support, SRC=tmp):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def have_docling():
    try:
        import docling                                       # noqa: F401
        return True
    except ImportError:
        return False


def slow_on():
    return bool(os.environ.get("BOOKSMITH_TESTS_SLOW"))


# Why a mutation may be unrunnable. A skip is printed aloud with its reason:
# an unrun mutation is not a caught one.
NEEDS = {"no_docling_package": have_docling,
         "slow_only": slow_on}


# --- broken editions of the guarded places ---------------------------------

def guard_without_words(page):
    """A guard that forgot the word "ours": everything reads as model rank."""
    return True


def truth_state_defaults_to_marked(page):
    """The old edition: a silent truth counts as annotated."""
    m = page.get("meta") or {}
    return metrics.ORDER_MARKED if m.get("order_marked", True) \
        else metrics.ORDER_UNMARKED


def pipeline_touches_at_off(self, blocks, w, h, index):
    """The pipeline "does nothing", yet rebuilds the list and adds a key."""
    return list(blocks), {"reading_order": "ours_top_down_left_right",
                          "docling_pipeline": {"mode": "off"}}


class GuessingTranslation(dict):
    """Labels translated by rule: whatever I do not know is text."""

    def get(self, key, default=None):
        return dict.get(self, key, "text")


def check_against_the_union(labels, policy_name="PP-DocLayoutV2"):
    """Checked against the union of dictionaries, not the named one."""
    have, mine = set(labels), set(policy.ROLE)
    if have - mine or mine - have:
        raise policy.UnknownLabel("объединение не сошлось")


def check_that_forgives(labels, policy_name="PP-DocLayoutV2"):
    """A default instead of a failure: the paddlex threshold-dict trouble."""


class GuessingRole(dict):
    def __missing__(self, key):
        return "text"


def span_takes_the_first(html, anchor):
    """Old edition: take the first mark -- no count, no inversion, no crossing."""
    o, c = swap.marks(anchor)
    return html.index(o) + len(o), html.index(c)


def span_without_crossing(html, anchor):
    """The "exactly one" count is here, the neighbour-crossing check is not."""
    o, c = swap.marks(anchor)
    if html.count(o) != 1 or html.count(c) != 1:
        raise swap.AnchorError(f"метка {anchor}: открывающих {html.count(o)}, "
                               f"закрывающих {html.count(c)}")
    a, b = html.index(o) + len(o), html.index(c)
    if b < a:
        raise swap.AnchorError(f"метка {anchor} вывернута")
    return a, b


def span_calls_nesting_a_crossing(html, anchor):
    """Nesting taken for crossing: any foreign mark inside is a refusal."""
    a, b = span_without_crossing(html, anchor)
    for other in swap._marks_in(html[a:b]):
        if other != anchor:
            raise swap.AnchorError(f"метка {anchor} пересекается с {other}")
    return a, b


def marks_by_prefix(anchor):
    """A mark is recognised by prefix, not by name."""
    return swap.OPEN.split("{}")[0], swap.CLOSE.split("{}")[0]


def anchors_sorted(html):
    return sorted(_real_anchors(html))


def anchors_swallow_unterminated(html):
    """An unterminated comment silently yields an empty list."""
    out, i = [], 0
    head = swap.OPEN.split("{}")[0]
    while True:
        i = html.find(head, i)
        if i < 0:
            return out
        j = html.find("-->", i)
        if j < 0:
            return out
        out.append(html[i + len(head):j])
        i = j + 3


def swap_forgets_what_it_removed(html, anchor, fragment):
    a, b = _real_span(html, anchor)
    return html[:a] + fragment + html[b:], ""


_real_knob = knobs.knob


def knob_says_post(name):
    """The knob is off, yet the adapter receives `post`."""
    return "post" if name == "DOCLING_PIPELINE" else _real_knob(name)


def knob_returns_empty(name):
    return os.environ.get(name, "")


def knob_ignores_empty(name):
    """`os.environ.get(...) or default`: an empty string outside loses."""
    return os.environ.get(name) or knobs.KNOB[name].default


def snapshot_skips_debts():
    return {k.name: {"value": knobs.knob(k.name), "default": k.default,
                     "set_externally": k.name in os.environ, "what": k.what,
                     "debt": k.debt}
            for k in knobs.KNOBS if not k.debt}


def snapshot_only_artefacts(policy_name=None):
    return {"buckets": list(policy.ROLES), "vocabulary": policy_name,
            "by_label": {l: "artifact" for l in policy.artefacts()}}


def passthrough_with_defaults():
    return {k.name: knobs.knob(k.name) for k in knobs.KNOBS}


_real_span, _real_anchors = swap.span, swap.anchors


def flipped_role():
    r = dict(policy.ROLE)
    r["table"] = "text"
    return r


def duplicated_policy():
    p = dict(policy.POLICIES)
    p["docling_twin"] = dict(policy.DOCLING)
    return p


def egret_without_translation():
    d = dict(dh.EGRET_TO_DOCLING)
    d["Table"] = "Table"
    return d


def docling_egret_short():
    d = dict(policy.DOCLING_EGRET)
    d.pop("Table")
    return d


def knobs_with_phantom():
    return knobs.KNOBS + (knobs.Knob("FANTOM", "", "ручка без потребителя"),)


def knobs_with_duplicate():
    return knobs.KNOBS + (knobs.Knob("PAGE_DPI", "300", "она же второй раз"),)


def knobs_with_int_default():
    k = knobs.KNOBS[0]
    return (knobs.Knob(k.name, 144, k.what),) + knobs.KNOBS[1:]


# --- the mutations themselves ----------------------------------------------
# (name; what we break; which checks MUST go red)

def guard_case_sensitive(value):
    """A guard comparing case again -- the damage that once was the defect.

    The LIVE function is swapped, not the source: both readers
    (`metrics._model_has_rank`, `doc/html._ours`) take it at call time, so one
    damage reaches both. The contract is shared, so it should.
    """
    return isinstance(value, str) and value.strip().startswith("наш")


def _journal_without_taken(out_dir, j):
    """The journal forgot WHAT it removed. Nothing left to undo with, while
    `put` works as if nothing happened -- the trouble shows only on undo."""
    z = {k: [{**r, "removed": ""} for r in v] for k, v in j["swaps"].items()}
    return _save_journal(out_dir, {**j, "swaps": z})


def _journal_invents_a_stack(out_dir):
    """The journal answers with a stack where no swap happened: "nothing to
    undo" and "the undo failed" stop being different answers."""
    return {"book": "book.html",
            "swaps": {"p0042-b17": [{"when": "?", "placed_by": "?", "kind": "html",
                                      "sha256_placed": "0" * 64,
                                      "removed": "<i>выдумка</i>",
                                      "sha256_removed": "0" * 64}]}}


def _flat_journal(out_dir, j):
    """The undo stack collapsed into its last value: intermediate states
    vanish silently and "redo it with another model" stops being reversible."""
    return _save_journal(out_dir, {**j, "swaps": {k: v[-1:] for k, v in
                                                   j["swaps"].items()}})


_save_journal = ap.save_journal



# ---- SECOND LEVEL: the reading guards ------------------------------------
# Every `test_read` check used to be covered by no mutation at all, and the
# runner printed that honestly.

def crop_dpi_by_the_whole_box(box, page_dpi, native, window, sheet=None):
    """Old rule: the clamp computed on the FULL box while what gets cut is the
    intersection with the sheet. A box hanging over got 83.7 dpi, not 118.4."""
    return vrun.crop_dpi_for(box, page_dpi, native, window, sheet=None)


def crop_dpi_stretches_up(box, page_dpi, native, window, sheet=None):
    """Stretch a small block up to the model's lower bound -- invented dots.

    The temptation is real: 555 crops of 566 are below the window. But above
    the scan's grid what is added is not ink, it is the rasteriser's guess.
    """
    base = float(native or page_dpi)
    if not window:
        return base, "своя резкость скана (границ модели нет)"
    lo, hi = window
    w = (box[2] - box[0]) / page_dpi
    h = (box[3] - box[1]) / page_dpi
    if w <= 0 or h <= 0:
        return base, "native_scan_dpi"
    at = w * base * h * base
    if at > hi:
        return (hi / (w * h)) ** 0.5, "downscaled_to_model_max"
    if at < lo:
        return (lo / (w * h)) ** 0.5, "растянуто до нижней границы модели"
    return base, "native_scan_dpi"


def crop_dpi_ignores_the_window(box, page_dpi, native, window, sheet=None):
    """The model window is never asked: always cut at our own dpi."""
    return float(native or page_dpi), "native_scan_dpi"


_SHAPE = replay.shape       # taken before the swap, or the breaker calls itself


def shape_silent_about_underived(snap):
    """The old `replay.shape`: an underivable shape demanded nothing.

    The "fingerprint" branch never entered the requirements AT ALL: a snapshot
    with no fingerprint passed `books replay --check` with code 0 and "51 of 51
    values in the snapshot, 0 missing", the word VERIFIED beside it.
    """
    r = _SHAPE(snap)
    if r["not_derived"]:
        r["not_derived"], r["derived"] = 0, []
    return r


def skip_by_what_is_installed(reason):
    """The old `support.skip`: chosen by whether pytest imports.

    Under our runner the first skip went past `run_case`'s handlers and killed
    the whole run: pytest's `Skipped` inherits BaseException.
    """
    try:
        import pytest
    except ImportError:
        raise support.Skip(reason) from None
    pytest.skip(reason)


def skip_always_ours(reason):
    """The skip is always ours -- under pytest that counts as a FAILURE."""
    raise support.Skip(reason)


def variants_built_once_at_defaults(M):
    """The old `metrics._order_variants`: finished pages, not builders.

    The "column by column" floor was built at the defaults yet measured across
    the whole sweep, and at overlap x 0.8/0.9 it outran the model itself.
    """
    return {"as_model_gave": M,
            "top_down_left_right": metrics._by_reading(M),
            "column_by_column": metrics._by_columns(M),
            "round_robin_columns": metrics._mix_columns(M)}


def ranking_without_rebuilding(variants, grid=None, cross=False,
                               key="per_page"):
    """The verdict is computed on variants that were NOT rebuilt: the builder
    is called without the point's parameters, so rebuilding is words only."""
    names = list(variants)
    pts = metrics._sweep_points(grid or metrics.COLUMN_SWEEP, cross)
    vals = {n: [] for n in names}
    for p in pts:
        for n in names:
            v = variants[n]
            vals[n].append(metrics.column_jumps(v() if callable(v) else v,
                                                **p)[key])
    return {"ranges": {n: (None, None) for n in names}, "stable": True,
            "by_point": [], "flipped_pairs": [], "tied_pairs": [],
            "points": len(pts), "variants": len(names), "pairs": 0,
            "pairs_distinguished": 0, "ruler_play": None,
            "closest_pair_at_default": None, "quantity": key}


def native_dpi_by_the_sheet(page):
    """Old formula: pixels divided by the width of the SHEET.

    A spread scan is WIDER than the sheet, so the grid was overstated by that
    ratio -- up to 2.47x on four books of six. Against the djvu header: the
    format declares 300/600/300, the old formula gave 741.9/600.0/621.7.
    """
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    best = 0.0
    for im in page.get_images(full=True):
        xref, w_px = im[0], im[2]
        if w_px <= 0:
            continue
        for r in page.get_image_rects(xref):
            if r.width < w_pt * 0.9:
                continue
            best = max(best, w_px / w_pt * 72.0)
    return best or None


def native_dpi_takes_any_image(page):
    """The "covers the sheet" floor is gone: a stamp in the corner decides
    for the whole page."""
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    best = 0.0
    for im in page.get_images(full=True):
        xref, w_px = im[0], im[2]
        for r in page.get_image_rects(xref):
            if r.width > 0 and w_px > 0:
                best = max(best, w_px / float(r.width) * 72.0)
    return best or None



# ---- FITNESS BY INK: guards for the ruler that chose the detector --------
# The only one of the three nobody had taken apart, and it held eight defects.
# Fixing them moved none of the eighteen bench numbers, so what is written in
# `docs/contour-notes.md` stands; what was missing were the guards.

def clip_that_trusts_numpy(shape, box):
    """Old clipping: numpy trims the top end and not the bottom one.

    `m[max(0,int(y0)):int(y1)+1]` with a negative `y1` counts the end FROM THE
    END of the array: box [-40,-40,-20,-20] on a 100x100 sheet covered 6561
    pixels of 10 000, so the metric could be won with garbage.
    """
    x0, y0, x1, y1 = (int(v) for v in box)
    return slice(max(0, y0), y1 + 1), slice(max(0, x0), x1 + 1)


def carried_as_text_by_double_counting(sub, arte, rest, tot):
    """A sum instead of a union: a pixel under two boxes counts twice.

    On `hard36`: "carried as text" 21 as it stands, 31 when doubled. Raw
    `docling-heron` has 4435 doubled pairs as normal behaviour, so "half the
    ink covered by nothing" was rewritten into "not lost, fixable by a label".
    """
    return (int((sub & arte).sum()) + int((sub & rest).sum())) / tot >= fit.WHOLE


def report_of_the_previous_edition(res, log=print):
    """The old report: one threshold of four, no dpi, no word about blindness
    to merging, and three different zeroes in two lines."""
    n = res["objects"]
    ink = max(1, res["ink_total"])
    log(f"страниц {res['page_count']}; порог чернил {fit.INK}, "
        f"«цел» от {fit.WHOLE:.2f} чернил объекта")
    log(f"чернил страницы под рамками: {res['ink_under_boxes'] / ink * 100:.1f}%, "
        f"вне всех рамок {(1 - res['ink_under_boxes'] / ink) * 100:.1f}% — "
        f"это то, что исчезнет из HTML")
    if not n:
        log("истина не подана: по объектам сказать нечего — это не ноль потерь")
        return
    log(f"объектов {n}: цел {res['intact']}")


def ink_memory_that_clears_itself(pdf, doc, i, dpi):
    """A cap counted in PAGES, cleared wholesale on overflow.

    64 pages -- 64 renders over seven passes; 65 pages -- 455. From full saving
    to none over one page, and on the very bench (600 pages) it was built for.
    """
    key = (pdf, i, int(dpi), fit.INK)
    if key not in fit._INK_CACHE:
        if len(fit._INK_CACHE) >= 64:
            fit._INK_CACHE.clear()
        m = fit._ink(doc[i], dpi)
        fit._INK_CACHE[key] = (m.shape, m)
    return fit._INK_CACHE[key][1]


def ink_memory_that_evicts_the_oldest(pdf, doc, i, dpi):
    """A cap in bytes, bit-packed -- and still zero saving.

    Evicting the oldest under a SEQUENTIAL walk misses by construction: the
    next pass starts on exactly what was evicted. Simulated on the real access
    trace and page shapes of the golden bench, 23 passes over 600 pages, cap
    512 MiB: 2400 renders against 1800, and 4800 against 3600 on two books.
    """
    import numpy as np
    key = (pdf, i, int(dpi), fit.INK)
    hit = fit._INK_CACHE.get(key)
    if hit is None:
        m = fit._ink(doc[i], dpi)
        packed = np.packbits(m)
        while (fit._INK_CACHE
               and fit._INK_CACHE_BYTES + packed.nbytes > fit._INK_CACHE_MAX_BYTES):
            fit._INK_CACHE_BYTES -= fit._INK_CACHE.pop(
                next(iter(fit._INK_CACHE)))[1].nbytes
        fit._INK_CACHE[key] = (m.shape, packed)
        fit._INK_CACHE_BYTES += packed.nbytes
        return m
    shape, packed = hit
    return np.unpackbits(packed, count=shape[0] * shape[1]).reshape(shape).view(bool)


def ink_memory_without_the_threshold(pdf, doc, i, dpi):
    """The ink threshold fell out of the memory key: changing it returned a
    mask computed with the OLD threshold, and a live knob looked dead."""
    key = (pdf, i, int(dpi))
    if key not in fit._INK_CACHE:
        m = fit._ink(doc[i], dpi)
        fit._INK_CACHE[key] = (m.shape, m)
    return fit._INK_CACHE[key][1]


@contextmanager
def source_swap(rel, old, new):
    """`support.tree(rel)` returns a parse of the SOURCE WITH ONE LINE SWAPPED.

    Checks that read a file by parsing look at the disk and never see
    `one_line`'s rebuilt module. Such checks exist here: a contract value can
    be a literal inside a method, and running it would mean loading a 216 MB
    model. Without this they count as uncoverable -- which happened: a sceptic
    removed the "cv2 filter" field from the tree copy and the battery declared
    itself sound.
    """
    import ast
    src = io_open_src(rel)
    if old not in src:
        raise AssertionError(
            f"мутация не наложилась: в {rel} нет строки {old!r} — "
            f"проверяемое место переписали, а батарея этого не знает")
    was = support.tree
    def swapped(r):
        if r == rel:
            return ast.parse(src.replace(old, new, 1), filename=r)
        return was(r)
    support.tree = swapped
    try:
        yield
    finally:
        support.tree = was


def io_open_src(rel):
    with open(os.path.join(support.SRC, rel), encoding="utf-8") as f:
        return f.read()


@contextmanager
def one_line(modname, old, new):
    """A module rebuilt from source with ONE line changed.

    `attrs` swaps what has a name in the module and cannot reach a line inside
    a long function; three checks counted as "uncoverable" for that, though
    their defects are line-sized. The rebuilt module goes into `sys.modules`
    AND onto the package as an attribute -- the second is required, or `from
    booksmith import fitness` in a reloaded check takes the old module and the
    mutation goes unnoticed. This changes BEHAVIOUR; `sources` is for checks
    that read the file from disk.
    """
    mod = importlib.import_module(modname)
    with open(mod.__file__, encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        raise AssertionError(
            f"мутация не наложилась: в {modname} нет строки {old!r} — "
            f"проверяемое место переписали, а батарея этого не знает")
    pkg, _, leaf = modname.rpartition(".")
    fake = importlib.util.module_from_spec(mod.__spec__)
    exec(compile(src.replace(old, new, 1), mod.__file__, "exec"), fake.__dict__)
    parent = sys.modules[pkg]
    sys.modules[modname] = fake
    setattr(parent, leaf, fake)
    try:
        yield
    finally:
        sys.modules[modname] = mod
        setattr(parent, leaf, mod)


_REAL_FIT_MUT = fit.mutations


def battery_summary_without_the_unmeasured(pdf, detect_dir, truth_dir="",
                                           log=print):
    """The battery's summary as the word "done": "9 probes, 0 missed" got
    printed even when five probes of nine measured nothing."""
    out = []
    rc = _REAL_FIT_MUT(pdf, detect_dir, truth_dir, log=out.append)
    for line in out:
        if "нечем мерить" in line or "measured" in line:
            continue
        log(line)
    return rc


def battery_that_corrupts_only_the_model(pdf, detect_dir, truth_dir="",
                                         log=print):
    """Only the model's output is corrupted. Not the TRUTH (a truth-blind
    metric measures its one input), not OUR OWN THRESHOLDS (a dead one prints
    like a live one). Proved by `T = M`: the old battery did not catch it."""
    out = []
    rc = _REAL_FIT_MUT(pdf, detect_dir, truth_dir, log=out.append)
    for line in out:
        if "истин" in line.lower() or "порог" in line.lower():
            continue
        log(line)
    return rc




def veto_measures_the_share_of_rows(pix, x):
    """Defect restored: the veto measures the SHARE of full-width rows.

    Quantised -- on a 599-row probe it means "three rows and not one fewer" --
    and the height of the scan decides: 3/599 = 0.005008 vetoes, 3/601 =
    0.004992 does not. Of 379 spreads of the Spravochnik, 102 (27%) turned on
    ONE row.
    """
    full_width, _ = djvu.dark_rows(pix, x)
    return djvu.RULE_RUN if len(full_width) / max(1, pix.height) > 0.005 else 0.0


def veto_looks_at_the_whole_probe(pix, x):
    """Defect restored: the border strip of the probe is not cut off.

    The black edge of the scan counts as a table rule again: 44 false vetoes of
    379 spreads of the Spravochnik, and the book rebuilds into 716 pages
    instead of 760.
    """
    runs = [ln for _, ln in djvu.dark_runs(pix, x)]
    return (max(runs) if runs else 0) / max(1, pix.width)



def routes_guess_by_role(self):
    """The route is DERIVED from the role instead of declared. That is how a
    twenty-sixth class in new weights would silently ride the text prompt."""
    from booksmith.read import Route
    from booksmith import policy
    out = {}
    for lab in policy.POLICIES[self.policy_name]:
        out[lab] = Route("OCR:", "text")
    return out


def cover_forgives(self, labels):
    """`cover` forgives a label with no route."""
    return None


def route_check_forgives(self, label):
    """The route checks neither the kind nor the reason for silence."""
    return None


def grid_only_from_html(s, kind=None):
    """Defect restored: a table is parsed from HTML only; OTSL goes blind."""
    from booksmith import text as _t
    return _t._html_grid(s)


def refusal_looks_like_silence(self, ask):
    """A delivery refusal recorded as model silence: two zeroes merged."""
    from booksmith.read import Said
    return Said(anchor=ask.anchor, text="", finish="stop")


def transport_check_only_pings(self, model=None):
    """The check asks "are you alive", not "what is your name"."""
    return {"endpoint": self.server, "models_on_server": [], "asking_for": model,
            "matched": True}


# ---- SECOND LEVEL: the book pass, transport, answer parsing --------------
# `test_read` and `test_text` stood in the runner's "no mutation" list: they
# guarded in appearance only. Money runs through the second level and `books
# text` is the ruler the model will be judged by, so both must go red on a
# PLAUSIBLE defect -- one a person would write, not a stub that throws. Where
# there is no seam the damage returns the QUANTITY the defect would: the guards
# of `measure_pages` and `read_book` sit inside two-hundred line functions, and
# a whole function replaced by a copy would prove only that the copy differs.

_real_send = vhttp.Http.send
_real_http_init = vhttp.Http.__init__
_real_data_uri = vhttp._data_uri
_real_to_json = Said.to_json
_real_read_book = vrun.read_book
_real_sniff = vrun._sniff
_real_detect_facts = vrun._detect_facts
_real_parse, _real_grid = otsl.parse, otsl.grid
# The real replacement wrapper, taken before any damage: the damage calls it
# with one argument changed, or it would test the wrong place.
_real_wrap = ap._wrap_fragment
_real_routes = PaddleOcrVl.routes
_real_reader_fingerprint = PaddleOcrVl.fingerprint
_real_measure = booktext.measure_pages
_real_truth_text = booktext._truth_text


def send_asks_again_on_silence(self, ask):
    """An empty answer is asked again: "it said nothing, I will re-ask".

    Fixing the model in its purest form, and it costs: a 200 with an empty body
    is an ANSWER, its generation already paid for.
    """
    said = _real_send(self, ask)
    if said.answered() and not (said.text or "").strip():
        said = _real_send(self, ask)
    return said


def http_takes_retries_for_attempts(self, server=None, model=None):
    """`VLM_RETRIES` read as the number of ATTEMPTS, not of retries.

    Off by one in `range(max(1, self.retries + 1))`: two retries give two
    requests, and "repeat while there was no answer" is silently shortened. On
    a long table that is a delivered answer against a delivery refusal.
    """
    _real_http_init(self, server, model)
    self.retries = max(0, self.retries - 1)


def data_uri_without_the_empty_guard(path):
    """The empty-crop guard is gone.

    On a blank white sheet this model produces full tables -- five different
    ones in five attempts -- and invention gets recorded as reading.
    """
    ext = os.path.splitext(path)[1].lower()
    raw = open(path, "rb").read()
    return ("data:" + vhttp.MIME[ext] + ";base64,"
            + base64.b64encode(raw).decode(), len(raw))


def data_uri_shrinks_the_crop(path):
    """Shrink the crop so it fits the context.

    OTHER bytes reach the model while the snapshot swears the very crop was
    sent. It happened at the first level already: a loop variable overwrote the
    scale factor and 36 pages of 36 were recorded unparsed on flawless answers.
    """
    uri, n = _real_data_uri(path)
    head, b64 = uri.split(",", 1)
    raw = base64.b64decode(b64)[:max(1, n // 2)]
    return head + "," + base64.b64encode(raw).decode(), len(raw)


def said_json_without_finish(self):
    """The answer record forgot HOW generation ended.

    A table cut off at the ceiling is indistinguishable from a whole one, and
    the vendor's `otsl_pad_to_sqr_v2` returns it plausible and short: the fifth
    zero merges with the first.
    """
    d = _real_to_json(self)
    d.pop("outcome", None)
    return d


def said_json_strips_the_text(self):
    """Trim the extra spaces so the book looks tidy.

    Editing the model's BYTES. What was recognised is untouchable, and that
    rule already cost nine misses of thirty-three.
    """
    d = _real_to_json(self)
    if isinstance(d.get("text"), str):
        d["text"] = d["text"].strip()
    return d


def said_json_writes_the_guess_into_the_text(self):
    """The kind guess appended INTO THE TEXT instead of beside it.

    The trouble for which the observed side lives in its own file, tied to the
    block by anchor: the mark was appended before the caption was read.
    """
    d = _real_to_json(self)
    if isinstance(d.get("text"), str) and d["text"]:
        d["text"] += "  <!-- вид: " + _real_sniff(d["text"]) + " -->"
    return d


def routes_read_the_pictures_too(self):
    """Ask about pictures too -- "there might be captions in there".

    Measurement rejected it: callouts unread, an invented pangram on two pages,
    a runaway loop on a third, +2100 words of garbage over twenty. And "not
    asked" stops being its own zero: two silences merge into one.
    """
    r = _real_routes(self)
    for lab, rt in list(r.items()):
        if not rt.asked():
            r[lab] = Route("OCR:", "text")
    return r


def reader_fingerprint_with_the_address(self):
    """The ADDRESS added to the reader's fingerprint, "to see where we went".

    It changes from run to run (the stub server's port, the loopback on the
    box), "what read it" never matches, and resuming re-asks the whole book --
    for money.
    """
    d = _real_reader_fingerprint(self)
    d["endpoint"] = knobs.knob("VLM_ENDPOINT")
    return d


def reader_fingerprint_without_prompts(self):
    """Prompts dropped from the fingerprint, "the snapshot is fat already".

    The prompt is the only thing here that steers the answer: not recording it
    means not recording the run.
    """
    d = _real_reader_fingerprint(self)
    d.pop("prompts", None)
    return d


def detect_facts_refresh_the_hash(detect_dir):
    """The detection snapshot "fixed": the book's sha256 recomputed from
    whatever file lies there now.

    This is how the trouble gets fixed the first time, the check having
    "broken" on a rented machine. Afterwards it compares the file with itself
    and always agrees: boxes from one file, crops from another, the answer
    looking like reading.
    """
    f = _real_detect_facts(detect_dir)
    p = (f.get("source") or {}).get("path")
    if p and os.path.exists(p):
        f = {**f, "source": dict(f["source"], **{"sha256": stamp.sha256(p)})}
    return f


def read_book_shrugs_at_zero_pages(*a, **kw):
    """The "not a single page to read" guard is gone: there is a check for an
    empty directory above and a second looks redundant. A typo in `--pages`
    then reports zeroes and code 0 -- an empty run looks successful."""
    try:
        return _real_read_book(*a, **kw)
    except SystemExit as e:
        if "ни одной страницы" not in str(e):
            raise
        return {"page_count": 0, "block_count": 0, "asked": 0, "not_asked": 0,
                "read": 0, "model_silent": 0, "delivery_failed": 0,
                "hit_ceiling": 0, "reused_from_previous_run": 0,
                "by_kind": {}}


def sniff_calls_emptiness_text(text):
    """An empty answer is sniffed like any other and declared text.

    "Empty" and "prose" are different zeroes: merged, the model's silence stops
    being visible in the observed side.
    """
    out = _real_sniff(text)
    return "text" if out == "empty" else out


def parse_pads_like_the_vendor(s):
    """Vendor-style parsing, as in `otsl_pad_to_sqr_v2`: rows are padded
    silently, tearing is NOT counted, and a table torn at the ceiling comes
    back plausible."""
    g, t = _real_parse(s)
    return g, dict(t, **{"rows_of_unequal_length": 0, "continuations_to_nowhere": 0})


def torn_grid_trusts_the_tearing_counters(g):
    """Tearing is counted, so the shape needs no checking.

    The error that let `p0055-b11` into the book: its tearing counters are all
    clean because the answer holds not one `<nl>` and 2047 cells in one row. A
    zero from not understanding in place of a zero from checking.
    """
    if not g:
        return None
    if g.get("continuations_to_nowhere") or g.get("rows_of_unequal_length"):
        return "рваная сетка"
    return None


def torn_grid_calls_any_single_row_impossible(g):
    """One row is suspicious enough, no floor needed.

    The inverse damage: a rule without a bound calls a lawful one-row `1x2`
    header impossible, and the number stops meaning anything.
    """
    if not g:
        return None
    if (g.get("rows") or 0) == 1:
        return "одна строка"
    return None


def observed_swallows_a_broken_answers_file(detect_dir):
    """One broken file, so drop everything observed.

    A quiet loss on the side: the book builds, "truncated at the ceiling"
    prints 0, and that zero is from not understanding.
    """
    import glob as _g
    import json as _j
    out = {}
    for fp in sorted(_g.glob(os.path.join(detect_dir, "answers", "*.json"))):
        with open(fp, encoding="utf-8") as f:
            try:
                recs = _j.load(f).get("answers") or []
            except ValueError:
                return {}
        for r in recs:
            if r.get("anchor"):
                out[r["anchor"]] = {"outcome": r.get("outcome"),
                                   "otsl_grid": (r.get("observed") or {}
                                                  ).get("otsl_grid")}
    return out


def parse_keeps_only_the_span_root(s):
    """A continuation is not a cell, it needs no addresses.

    Breaks the contract the reading ruler stands on: a two-column header stops
    occupying the second column, a shifted row is compared against emptiness,
    and a right number gets printed for wrong reasons.
    """
    g, t = _real_parse(s)
    if not g:
        return g, t
    from_tags = otsl._TOK.findall(s)
    ours, r, c = {}, 0, 0
    for name in from_tags:
        if name in otsl.BREAK:
            r, c = r + 1, 0
            continue
        if name not in otsl.SPAN:
            ours[(r, c)] = g.get((r, c), "")
        c += 1
    return (ours or None), t


def to_html_is_a_stub(s):
    """THE damage that used to pass unnoticed.

    A sceptic replaced `to_html` with a stub: 202 checks, 0 failures, 181
    mutations, not one red -- though this function builds ALL 104 tables of the
    book (verified byte for byte). It stays here forever: uncoveredness must be
    visible as a number, not as memory.
    """
    return "<table><tr><td>ТРУХА</td></tr></table>"


def to_html_flattens_every_span(s):
    """Old behaviour: spans expanded into repeats.

    Why the book held 104 tables with `colspan` 0 and `rowspan` 0, and the
    header "Years" printed six times in a row.
    """
    import html as _h
    g, _ = _real_parse(s)
    if not g:
        return ""
    rows = max(r for r, _ in g) + 1
    cols = max(c for _, c in g) + 1
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        for c in range(cols):
            out.append("<td>" + _h.escape(g.get((r, c), "")) + "</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def to_html_merges_equal_neighbours(s):
    """A guess instead of a tag: equal neighbours count as a merge.

    On this book it would lie in 13 tables of 62, where equal neighbouring
    cells stand WITHOUT a single `<lcel>`.
    """
    import html as _h
    g, _ = _real_parse(s)
    if not g:
        return ""
    rows = max(r for r, _ in g) + 1
    cols = max(c for _, c in g) + 1
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        c = 0
        while c < cols:
            v = g.get((r, c), "")
            w = 1
            while c + w < cols and g.get((r, c + w), "") == v:
                w += 1
            out.append(f'<td colspan="{w}">' if w > 1 else "<td>")
            out.append(_h.escape(v) + "</td>")
            c += w
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def to_html_opens_a_row_only_where_a_root_is(s):
    """Old walk: `<tr>` opens when the row number of a CELL changes.

    A row made entirely of continuations gets no `<tr>`, and the rows after it
    slide right by the number of merged columns.
    """
    import html as _h
    from booksmith import otsl as _o
    cs, _ = _o.layout(s)
    if not cs:
        return ""
    out, r = ["<table>"], None
    for cell in cs:
        if cell["row"] != r:
            if r is not None:
                out.append("</tr>")
            out.append("<tr>")
            r = cell["row"]
        tag = "th" if cell["tag"] in _o.HEADER else "td"
        span = ""
        if cell["cols"] > 1:
            span += f' colspan="{cell["cols"]}"'
        if cell["rows"] > 1:
            span += f' rowspan="{cell["rows"]}"'
        out.append(f"<{tag}{span}>" + _h.escape(cell["text"]) + f"</{tag}>")
    out.append("</tr></table>")
    return "".join(out)


def to_html_pads_short_rows(s):
    """A short row padded with empty cells: invention in place of tearing."""
    import html as _h
    from booksmith import otsl as _o
    cs, t = _o.layout(s)
    if not cs:
        return ""
    by = {}
    for c in cs:
        by.setdefault(c["row"], []).append(c)
    rows = max(t["rows"], max(by) + 1)
    wider = max((c["col"] + c["cols"] for c in cs), default=0)
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        taken = 0
        for cell in by.get(r, ()):
            tag = "th" if cell["tag"] in _o.HEADER else "td"
            out.append(f"<{tag}>" + _h.escape(cell["text"]) + f"</{tag}>")
            taken += cell["cols"]
        out.extend(["<td></td>"] * max(0, wider - taken))
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def layout_gives_the_split_span_our_default_tag(s):
    """An expanded merge gets our `fcel` instead of the root's tag."""
    from booksmith import otsl as _o
    cs, t = _o.layout(s)
    out = []
    for c in cs:
        if c["rows"] == 1 and c["cols"] == 1:
            out.append(dict(c, **{"tag": "fcel"}))
        else:
            out.append(c)
    return out, t


def to_html_calls_the_first_row_a_header(s):
    """The guess "the first row is always a header" instead of `<ched>`."""
    import html as _h
    from booksmith import otsl as _o
    cs, _ = _o.layout(s)
    if not cs:
        return ""
    out, r = ["<table>"], None
    for cell in cs:
        if cell["row"] != r:
            if r is not None:
                out.append("</tr>")
            out.append("<tr>")
            r = cell["row"]
        tag = "th" if cell["row"] == 0 else "td"
        span = ""
        if cell["cols"] > 1:
            span += f' colspan="{cell["cols"]}"'
        if cell["rows"] > 1:
            span += f' rowspan="{cell["rows"]}"'
        out.append(f"<{tag}{span}>" + _h.escape(cell["text"]) + f"</{tag}>")
    out.append("</tr></table>")
    return "".join(out)


def layout_straightens_a_torn_span(s):
    """A non-rectangular merge straightened silently: fixing the model.

    The vendor's `otsl_pad_to_sqr_v2` does exactly this, and a torn table comes
    back plausible.
    """
    from booksmith import otsl as _o
    cs, t = _o.layout(s)
    return cs, dict(t, **{"non_rectangular_merges": 0})


def wrap_fragment_drops_the_torn_mark(anchor, fragment, kind, source,
                                      role="unknown", torn=None):
    """The wrapper drops the truncation mark, exactly as before the fix.

    The book kept 10 marks of 14, and the four lost were the ones that reached
    the reader as markup: a truncated table, a truncated formula, a truncated
    chart.
    """
    return _real_wrap(anchor, fragment, kind, source, role=role, torn=None)


def wrap_fragment_marks_everything_torn(anchor, fragment, kind, source,
                                        role="unknown", torn=None):
    """The inverse damage: "not asked" passed off as "truncated".

    A mark on everything is the same as no mark: it stops meaning anything,
    while `books read` honestly knows the difference.
    """
    return _real_wrap(anchor, fragment, kind, source, role=role, torn=True)


def shape_of_a_placed_block_is_never_asked(g):
    """The shape of a placed fragment is never judged."""
    return None


def repeats_compare_the_block_with_itself(page, covered):
    """THE error: a block looked for in prose that includes the block itself.

    Gives 99.0 % where 21.4 % is right, and declares ANY nested block a repeat,
    including one whose text exists nowhere else.
    """
    from_text = [b for b in page.blocks
                 if policy.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    whole_page = " ".join(booktext.normalize(b.content, "latex") for b in from_text)
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        owners = [o for o in from_text
                   if o.block_id != b.block_id and covered(b.box, o.box)]
        own = booktext.normalize(b.content, "latex")
        out[b.block_id] = (owners[0].block_id if owners else None,
                           "verbatim" if len(own) >= 2 and own in whole_page
                           else "differs")
    return out


def repeats_compare_with_other_candidates_too(page, covered):
    """Compared against ALL blocks, other candidates included.

    Two equal repeats hide each other and neither stays in the book: each "is
    present in the neighbour".
    """
    from_text = [b for b in page.blocks
                 if policy.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        others = " ".join(booktext.normalize(o.content, "latex")
                          for o in from_text if o.block_id != b.block_id)
        owners = [o for o in from_text
                   if o.block_id != b.block_id and covered(b.box, o.box)]
        own = booktext.normalize(b.content, "latex")
        out[b.block_id] = (owners[0].block_id if owners else None,
                           "verbatim" if len(own) >= 2 and own in others
                           else "differs")
    return out


def bare_math_eats_the_command_name(s):
    """Presentational commands stripped along with meaningful ones.

    `\alpha` and `\beta` become emptiness and match, so the ruler declares two
    different formulas equal.
    """
    import re as _re
    if not s:
        return ""
    s = _re.sub(r"\\[a-zA-Z]+", " ", s.strip())
    return _re.sub(r"[{}\\$\[\]^_]", "", s).strip().casefold()


def _repeats_variant(page, covered, *, artifacts=False, empty=False,
                     always=None, threshold=None):
    """A shared damaged variant of the repeat rule: one trouble at a time."""
    from_text = [b for b in page.blocks
                 if (artifacts or policy.role(b.label) != "artifact")
                 and (empty or (b.content or "").strip())]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    stays = " ".join(booktext.normalize(b.content or "", "latex")
                        for b in from_text if b.block_id not in nested)
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        owners = [o for o in from_text
                   if o.block_id != b.block_id and covered(b.box, o.box)]
        own = booktext.normalize(b.content or "", "latex")
        lo = threshold if threshold is not None else dhtml.REPEAT_MIN
        # `why`, not `out`: the verdict once shared the name of the result
        # dict, overwrote it with a str, and the next line raised TypeError.
        # `reddens` counts any exception as red, so all four mutations built
        # on this helper were certified caught while modelling nothing --
        # exactly the "stub that throws" this file's own prose forbids.
        why = (always if always else
                 ("verbatim" if len(own) >= lo and own in stays
                  else "differs"))
        out[b.block_id] = (owners[0].block_id if owners else None, why)
    return out


def repeats_never_prove_anything(page, covered):
    """Nothing is ever proven a repeat: the ruler is silent, the book fat."""
    return _repeats_variant(page, covered, always="differs")


def repeats_prove_everything(page, covered):
    """Everything nested is declared a repeat, with no comparison at all."""
    return _repeats_variant(page, covered, always="verbatim")


def repeats_count_the_artefact_as_a_neighbour(page, covered):
    """A block nested in an artefact judged like a text one.

    It must not be hidden: if no replacement arrives, the picture stays the
    only form of that text.
    """
    return _repeats_variant(page, covered, artifacts=True)


def repeats_take_the_empty_block_too(page, covered):
    """An empty block becomes a candidate: there is nothing in it to match."""
    return _repeats_variant(page, covered, empty=True)


def why_empty_says_unread_for_everything(o):
    """All five zeroes collapse into one, as before the fix."""
    return "не прочитан"


def repeats_join_without_a_gap(page, covered):
    """The remaining blocks joined WITHOUT a gap: a match across the seam.

    A candidate is "found" at the junction of two other blocks and hidden
    falsely. Acceptance showed none of the eight checks caught it.
    """
    from_text = [b for b in page.blocks
                 if policy.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    kept = [b for b in from_text if b.block_id not in nested]
    glue = "".join(booktext.normalize(b.content, "latex") for b in kept)
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        own = booktext.normalize(b.content, "latex")
        found_one = len(own) >= dhtml.REPEAT_MIN and own in glue
        out[b.block_id] = (kept[0].block_id if kept else None,
                           "verbatim" if found_one else "differs")
    return out


def repeats_have_no_length_floor(page, covered):
    """The length floor is gone: a two-character match counts as proof."""
    return _repeats_variant(page, covered, threshold=1)


def repeats_trade_typeset_for_raw(page, covered):
    """The typeset form is hidden even when the carrier holds raw LaTeX."""
    out = dhtml.repeats_on(page, covered)
    return {k: (v[0], "verbatim" if v[1] == "layout" else v[1])
            for k, v in out.items()}


def repeats_name_the_enclosing_frame(page, covered):
    """The answer names the enclosing frame, not the carrier of the proof."""
    out = dhtml.repeats_on(page, covered)
    from_text = [b for b in page.blocks
                 if policy.role(b.label) != "artifact" and (b.content or "").strip()]
    fresh = {}
    for k, (_, why) in out.items():
        own = next(b for b in from_text if b.block_id == k)
        owners = [o for o in from_text
                   if o.block_id != k and covered(own.box, o.box)]
        box = min(owners, key=lambda o: o.area()) if owners else None
        fresh[k] = (box.block_id if box else None, why)
    return fresh


def torn_of_calls_the_unasked_whole(o):
    """No stop reason means it was read to the end.

    Merges 69 unasked pictures with 6073 honestly finished blocks.
    """
    return (o or {}).get("outcome") == "length"


def torn_grid_column_rule_has_no_floor(g):
    """The column rule loses its floor: a lawful two-cell column is declared
    an impossible table."""
    if not g:
        return None
    rows, cells = g.get("rows") or 0, g.get("grid_cells") or 0
    if rows == 1 and cells > 3:
        return f"вся таблица в одной строке: {cells} клеток"
    cols = (cells // rows) if rows else 0
    if cols == 1 and rows > 1:
        return f"вся таблица в одном столбце: {rows} строк"
    return None


def observed_invents_a_clean_bill_when_there_is_nothing(detect_dir):
    """No `answers/` means it was read and all is well.

    A detection directory without the second level has no observed side BY
    CONSTRUCTION. Passed off as health it prints "truncated 0" where the answer
    is "nothing to say it with".
    """
    return {"p0001-b0": {"outcome": "stop", "otsl_grid": None}}


def observed_keeps_anchors_and_drops_the_reason(detect_dir):
    """A list of anchors will do.

    The observed side arrives empty: the blocks are named, why they are bad is
    not. Exactly the state the pipeline lived in.
    """
    import glob as _g
    import json as _j
    out = {}
    for fp in sorted(_g.glob(os.path.join(detect_dir, "answers", "*.json"))):
        try:
            with open(fp, encoding="utf-8") as f:
                recs = _j.load(f).get("answers") or []
        except (ValueError, OSError):
            continue
        for r in recs:
            if r.get("anchor"):
                out[r["anchor"]] = {}
    return out


def grid_of_prose_is_an_empty_table(s):
    """Return an empty grid so the caller need not check for None.

    "Not OTSL" and "the table is empty" merge into one zero, and prose handed
    back in place of a table stops counting as handed back as text.
    """
    return _real_grid(s) or {}


def policies_with_a_new_class():
    """A twenty-sixth class from new weights appeared in the detector's
    dictionary and nobody gave it a reading route."""
    p = dict(policy.POLICIES)
    p["PP-DocLayoutV2"] = dict(p["PP-DocLayoutV2"], sidebar="text")
    return p


def span_ends_at_the_last_closing_mark(html, anchor):
    """The block's end found by the PREFIX of the closing mark: it is ours
    anyway. The replacement eats the neighbouring block whole, border included,
    and half the book ends up re-marked."""
    o, _c = swap.marks(anchor)
    return html.index(o) + len(o), html.rindex(swap.CLOSE.split("{}")[0])


def status_reads_only_the_journal(out_dir, log=print):
    """Old edition: `status` reads the JOURNAL and never opens the book.

    The anchor count comes from the journal, zero on an untouched book, so "the
    book is empty" is indistinguishable from "not walked yet".
    """
    j = ap.load_journal(out_dir)
    live = {k: len(v) for k, v in j["swaps"].items() if v}
    log(f"якорей в журнале {len(j['swaps'])}; заменено блоков {len(live)}, "
        f"всего замен {sum(live.values())}")
    if not j["swaps"]:
        log("якорей нет вовсе — это не «всё заменено», а пустая книга")
    return {"anchor_count": len(j["swaps"]), "blocks_swapped": len(live),
            "swaps_total": sum(live.values()), "fully_undone": 0,
            "drifted": 0, "missing_from_book": 0, "per_anchor": live}


def anchor_without_the_page(page_index, block_id):
    """A book-wide anchor with no page number: five hundred identical `b17` in
    a five-hundred-page book, and a replacement lands in the wrong place."""
    return f"b{block_id}"


# ---- THE READING RULER: `books text` -------------------------------------
# No seam to the `measure_pages` guards: the damage returns the quantity the
# defect would, and is named after the defect, not after the method.

def measure_scores_silence_as_zero(T, P, *a, **kw):
    """A block with no answer gets CER 0 instead of None: "it told no lies".

    Silence becomes flawless reading, the guard "there was NOTHING to compare"
    never fires, and the report ends with "CER 0 on all".
    """
    r = _real_measure(T, P, *a, **kw)
    for rec in r["per_block"]:
        if (rec.get("bucket") in ("text", "артефакт по истине")
                and rec.get("CER") is None):
            rec["CER"] = 0.0
    return r


def measure_calls_artefacts_text(T, P, *a, **kw):
    """An artefact filed under the role "text": the last line's numerator
    counts both roles again while the denominator counts one. Measured before
    the fix: "CER 0 on all 130 counted of 104" on a book of 104 text blocks."""
    r = _real_measure(T, P, *a, **kw)
    for rec in r["per_block"]:
        if rec.get("bucket") == "артефакт по истине":
            rec["bucket"] = "text"
    return r


def measure_counts_words_in_a_formula(T, P, *a, **kw):
    """Text and artefact branches merged, so a formula record carries `WER`.

    Words are not counted in a formula: meaningless, printed as measured. The
    ruler crashed on this very field -- "worst block" printed a `WER` an
    artefact does not have, and `books text` died with `KeyError` precisely
    when it had something to say.
    """
    r = _real_measure(T, P, *a, **kw)
    for rec in r["per_block"]:
        if (rec.get("bucket") == "артефакт по истине"
                and rec.get("CER") is not None):
            rec["WER"] = rec["CER"]
    return r


def measure_counts_silence_as_an_answer(T, P, *a, **kw):
    """Silence on an artefact counted as an ANSWER (an empty one).

    "Nothing to compare" turns into a measured "CER 1.0" -- a zero from not
    understanding, printed as a quantity.
    """
    r = _real_measure(T, P, *a, **kw)
    r["artifacts_with_truth"]["no_answer"] = 0
    return r


def measure_forgets_invention_on_empty_truth(T, P, *a, **kw):
    """The "invented on empty truth" counter removed, "it is not in CER".

    It really is invisible in CER (nothing to divide by), which is why
    invention over declared emptiness vanishes silently.
    """
    r = _real_measure(T, P, *a, **kw)
    r["artifacts_with_truth"]["invented_on_empty_truth"] = 0
    return r


def truth_text_reads_only_tables(b, side=None):
    """Old edition: the ruler never reads an artefact's character truth,
    looking beside the block for a table grid only.

    On `bench/matematika`: 26 formulas filled with truth byte for byte gave
    "baits: 26 artefacts, READ 26 (100%)" -- flawless reading declared
    invention throughout.
    """
    return None


def truth_text_empty_instead_of_none(b, side=None):
    """No truth means an empty string.

    A bait becomes an artefact with declared emptiness, and invention over a
    line drawing counts as correct work.
    """
    return _real_truth_text(b, side) or ""


def truth_both_chooses_silently(b, side=None):
    """The "both a grid and characters on one block" guard is gone: the table
    branch comes first and the characters are dropped silently -- the operator
    has been told which truth to believe."""
    return None


# ---- THE BOOK: journal, comments, crops ----------------------------------
# Checks added to `test_apply` and `test_html_order` during this very work: the
# second level's money runs through them too.

_real_load_journal = ap.load_journal
_real_cut = crop.cut
_real_params = crop.params


def comments_guard_is_off(body, anchor):
    """The fifth guard removed: the anchor check catches unclosed marks anyway.

    It does not: `swap.anchors` looks for `<!--bs:` and a bare `<!--` is no
    anchor to it. On a book of 26 blocks: "placed 154, removed 175, anchors
    26", while the browser ate our closing mark with the rest of the book.
    """
    return None


def comments_are_refused_wholesale(body, anchor):
    """The guard swings wide: any `<!--` in a replacement is a refusal.

    The second level may legitimately return markup with a comment inside, and
    a guard that forbids everything cannot NOT fire.
    """
    if "<!--" in body:
        raise ap.SwapError(
            f"в замене {anchor} комментарий открыт и не закрыт: {body[:40]!r}")


def journal_unreadable_is_an_empty_one(out_dir):
    """An unreadable journal taken for an empty one, "won't read, start over".

    The next replacement writes its single record over the stump, and the undo
    stack of the WHOLE book vanishes silently and irreversibly.
    """
    try:
        return _real_load_journal(out_dir)
    except ap.SwapError:
        return {"book": "book.html", "swaps": {}}


def journal_written_in_place(out_dir, j):
    """The journal written straight into place, with no temporary file.

    `open(p, "w")` truncates FIRST, before a byte is written: an interrupted
    write (no space, Ctrl-C, unmounted disk) leaves a stump where the whole
    book's undo stack was. 2101 bytes became 1076, unparsable as json.
    """
    p = os.path.join(out_dir, ap.JOURNAL)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    return p


def clipped_only_when_nothing_is_left(rect, clip) -> bool:
    """Clipped by the sheet read as nothing of the box is left.

    A box the sheet took a fifth of is declared whole: half a table goes into
    the book unmarked, and the "clipped" value can no longer fire.

    WHY THIS DAMAGE. The direct one -- exact comparison instead of a tolerance,
    the old defect -- is NOT VISIBLE here: at 150 dpi the coordinates 100 and
    300 points survive a float32 round trip exactly and the probe stays green.
    Its first half measures air; the second works ("a real clip must stay
    visible") and that is the half this breaks.
    """
    return bool(clip.is_empty)


def cut_without_the_named_troubles(doc, page_index, box, page_dpi, dst,
                                   **kw):
    """A degenerate and an inverted box get SOMEONE ELSE'S diagnosis again.

    Both give an empty intersection with the sheet, so without their own checks
    the reader is told "does not intersect the sheet" about a box in the middle
    of the paper, and hunts for drifted coordinates instead.
    """
    try:
        return _real_cut(doc, page_index, box, page_dpi, dst, **kw)
    except ValueError as e:
        if "ВЫРОЖДЕНА" in str(e) or "ПЕРЕВЁРНУТА" in str(e):
            raise ValueError(
                f"рамка {tuple(box)} на стр. {page_index} не пересекается с "
                f"листом") from None
        raise


def params_clamps_the_margin(page_dpi=None):
    """A negative `CROP_MARGIN` silently clamped to zero.

    The knob is declared live while it CUTS the model's box: at
    `CROP_MARGIN=-0.1` it ate a tenth from each side and both clipping values
    stood False.
    """
    def clamped(name):
        v = _real_knob(name)
        return "0" if name == "CROP_MARGIN" and float(v) < 0 else v

    with attrs(knobs, knob=clamped):
        return _real_params(page_dpi)


def params_takes_the_dpi_from_the_environment(page_dpi=None):
    """The crop dpi taken from the environment, not from DETECTION.

    `bench/atlas` detected at PAGE_DPI=150 and built at the default: "26 crops
    at 144 dpi" while the coordinates come from 150.
    """
    return _real_params(None)


def nesting_compares_raw_order(arts):
    """The old line: ranks compared as tuples `(order, block_id)`.

    The contract permits `Block.order = None` outright and three adapters give
    no rank, so a "rank / no rank" pair on one rectangle brings down the WHOLE
    book build: `TypeError: '>=' not supported between instances of 'NoneType'
    and 'int'`.
    """
    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    inner = {}
    for b in arts:
        for o in arts:
            if o.block_id == b.block_id or not dhtml._covered(b.box, o.box):
                continue
            ab, ao = area(b), area(o)
            if ab > ao * 1.02:
                continue
            if (abs(ab - ao) <= ao * 0.02
                    and (o.order, o.block_id) >= (b.order, b.block_id)):
                continue
            inner[b.block_id] = o.block_id
            break
    return inner


def sheet_trouble_with_two_marks(blocks, arts):
    """Old edition: a sheet fails in three ways and there were two marks.

    A sheet with one page number (`footer`, role "service") got the red "the
    whole page went into pictures" at `data-image-share="0.00"`, contradicting
    itself: `bench/atlas` page 0, and over the book "pages without a single
    text block" stood at 9 against eight real.
    """
    if not blocks:
        return "empty"
    if any(policy.role(b.label) == "text" for b in blocks):
        return None
    return "без-текста"


def anchor_of_a_private_copy(page_index, block_id):
    """`doc/feed` grew its OWN copy of the anchor rule.

    Today it matches character for character, and the copies will drift
    silently: feed.json naming fragments one way, the book and blocks.json
    another, `books apply` answering "no such anchor in the book" to every
    block read.
    """
    return f"p{page_index:04d}-b{block_id}"


# --- step 1 instruments: the Cyrillic ratchet and the key presence guard ----

def _walk_top_only(obj, counter):
    """A walk that does not descend.

    Exactly the failure the presence guard exists to catch: `text annotated`
    does NOT sit at the top level of a truth page, so a walk that counts only
    top-level keys declares it missing from all 1359 files at once.
    """
    if isinstance(obj, dict):
        for k in obj:
            counter[k] += 1


def _floors_zeroed():
    """Floors declared as zero: a guard that cannot say "too few"."""
    return tuple(schema.Format(f.name, f.pattern, {k: 0 for k in f.floors},
                               f.note) for f in schema.FORMATS)


def _globs_one_level_short():
    """The pattern loses a directory level -- the first draft of the
    declaration did exactly this: 636 files instead of 1272, half a floor
    wearing the look of a measured one."""
    return tuple(schema.Format(f.name, f.pattern.replace("/**/", "/"), f.floors,
                               f.note) for f in schema.FORMATS)


def _latin_is_not_counted(s):
    """Only the Cyrillic side is measured, so deletion looks like translation."""
    return 0


def _counter_that_skips_finished_files(s):
    """Latin counted as zero -- the shape the walk had when a file that was
    fully translated dropped out of it and took its Latin along."""
    return 0


def _baseline_of_deleted_prose():
    """A baseline that says 40 000 Cyrillic characters left and no English came.

    The mutation has to be the DISAPPEARANCE, not the counter: the check only
    speaks when Cyrillic actually falls, so breaking `latin()` alone leaves it
    with nothing to look at -- which is how the first version of this mutation
    went uncaught.
    """
    import tempfile
    base = json.loads(open(cyrmod.BASELINE, encoding="utf-8").read())
    now = cyrmod.count()
    for area in ("src.comments", "src.docstrings"):
        base[area] = base.get(area, 0) + 20000
        # AND the Latin side is pinned to what the tree holds right now.
        # Without that the mutation is toothless: while a real translation is
        # under way the Latin count rises on its own, covers the invented
        # loss, and the check stays honestly quiet. Caught by this very
        # battery, mid-translation.
        base[area + ".latin"] = now.get(area + ".latin", 0)
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False)
    return path


def _book_prose_folded_into_the_ratchet(c):
    """Book content stops being a separate area, so its loss is invisible."""
    out = {k: v for k, v in c.items() if not k.endswith(".latin")}
    out.pop("bench_data", None)
    return out


def _measure_finds_nothing(root=None):
    """The disk side of the guard goes quiet. The name side must notice."""
    return {f.name: {} for f in schema.FORMATS}


def _map_with_a_measurement():
    """A copy of the map with a moved figure written back into it."""
    return _map_plus("\n\nV2 finds 698 of 1232 on the golden bench.\n")


def _map_naming_a_missing_file():
    """A map that points at a file the tree does not have."""
    return _map_plus("\n\nSee `docs/there-is-no-such-file.md` for details.\n")


def _map_naming_a_ghost_command():
    """A map that offers a command the CLI never declared."""
    return _map_plus("\n\nbooks conjure                a command that is not\n")


def _map_plus(tail):
    import tempfile
    text = open(schema.DOC_MAP, encoding="utf-8").read()
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text + tail)
    return path


def _clock_not_stripped():
    """The wall clock stays in the report, so every line differs every run.

    A snapshot that never matches gets its expectations re-saved by the first
    person it annoys, and from then on it compares nothing.
    """
    import re
    return re.compile(r"^(?!)")


def _table_missing_a_format():
    """Only the help survives -- no snapshot reads truth, pages or a snapshot."""
    return {"help": acceptance.COMMANDS["help"]}


def mutations():
    m = [
        ("журнал не сохраняет снятое",
         lambda: attrs(ap, save_journal=_journal_without_taken),
         [("test_apply", "test_journal_keeps_what_was_taken"),
          ("test_apply", "test_put_then_undo_restores_the_book_byte_for_byte")]),

        ("вид содержимого принимается любой",
         lambda: attrs(ap, KINDS=ap.KINDS + ("markdown",)),
         [("test_apply", "test_unknown_kind_is_refused")]),

        ("журнал выдумывает стопку там, где замен не было",
         lambda: attrs(ap, load_journal=_journal_invents_a_stack),
         [("test_apply", "test_undo_without_a_swap_is_loud_and_distinct")]),

        ("сверка набора якорей после замены снята",
         lambda: attrs(ap, _anchors_unchanged=lambda a, b: True),
         [("test_apply", "test_unterminated_mark_is_caught_by_the_anchor_guard")]),

        ("замена не проверяет вставляемый кусок",
         lambda: attrs(ap, _check_fragment=lambda *a, **k: None),
         [("test_apply", "test_fragment_with_marks_is_refused_by_the_fragment_check"),
          ("test_apply", "test_empty_fragment_is_refused")]),

        ("стопка отката схлопнута в последнее значение",
         lambda: attrs(ap, save_journal=_flat_journal),
         [("test_apply", "test_stack_unwinds_in_reverse_order")]),

        ("откат не сверяет, что лежит на месте блока",
         lambda: attrs(ap, _same=lambda now, promised: True),
         [("test_apply", "test_edit_outside_the_journal_blocks_undo")]),

        ("сторож метрики не смотрит на слово «наш»",
         lambda: attrs(metrics, _model_has_rank=guard_without_words),
         [("test_order_contract", "test_guard_reads_every_value_as_intended")]),

        ("молчащая истина считается размеченной (беда hard36)",
         lambda: attrs(metrics, _truth_order_state=truth_state_defaults_to_marked),
         [("test_order_contract", "test_truth_side_has_three_answers_not_two")]),

        # THE PROBE WAS RE-AIMED, not dropped: it broke the adapter's
        # capitalisation and caught only because the guard compared case --
        # which was itself the defect, `doclayout.fingerprint` writing "OURS"
        # capitalised. Damaged now is a value absent from the contract table.
        # The guard takes it for MODEL RANK (it does not start with "ours") and
        # the metric prints a percentage over our own numbering: the hard36
        # trouble from the other end. The adapter's TAIL is damaged, not the
        # rule -- the rule is single (`order.WORDS`) and the table derives from
        # it, so swapping the rule moves both sides at once.
        ("адаптер завёл значение мимо таблицы договора",
         lambda: sources("models/doclayout.py",
                         '+ ": the model gives no rank"',
                         '+ " (ранга модель не даёт)"'),
         [("test_order_contract", "test_no_unknown_order_values")]),

        # The second reader of the contract is the book builder, and it used
        # to stand on trust: a private copy of its rule failed none of sixty
        # checks.
        # The copy differs only by NOT folding case -- which is precisely the
        # half the check is named for, and the half that stopped being
        # exercised when the probe values were left in Russian.
        ("the book builder keeps a copy of the order rule that ignores case",
         lambda: attrs(dhtml, _ours=lambda v: isinstance(v, str)
                       and v.strip().startswith("ours")),
         [("test_html_order",
           "test_book_builder_reads_the_order_rule_through_the_one_contract")]),

        ("сторож перестал снимать регистр",
         lambda: attrs(mbase, ours_order=guard_case_sensitive),
         [("test_order_contract", "test_guard_ignores_case")]),

        ("адаптер вовсе не сказал, чей порядок",
         lambda: sources("models/yolox_layout.py",
                         '"reading_order": order.WORDS[which],', ""),
         [("test_order_contract", "test_adapters_declare_order_rule_at_all")]),

        ("правило конвейера перестало начинаться со слова «наш»",
         lambda: attrs(dh._DoclingPipeline, ORDER_RULE={
             "post": "порядок docling", "full": "порядок docling"}),
         [("test_order_contract",
           "test_our_order_values_start_with_lowercase_nash")]),

        ("конвейер при off пересобирает рамки и дописывает ключ",
         lambda: attrs(dh.DoclingHeron, _run_pipeline=pipeline_touches_at_off),
         [("test_docling_pipeline", "test_off_returns_the_very_same_frames"),
          ("test_docling_pipeline", "test_off_adds_exactly_one_meta_key")]),

        ("ключ конвейера уехал в конец meta",
         lambda: sources("models/docling_heron.py",
                         "                  **pipe_meta,\n", ""),
         [("test_docling_pipeline",
           "test_off_keeps_meta_key_order_byte_for_byte")]),

        ("умолчание ручки переставили на full",
         lambda: attrs(knobs.KNOB["DOCLING_PIPELINE"], default="full"),
         [("test_docling_pipeline", "test_pipeline_default_is_off")]),

        ("в режимы ручки добавили четвёртый",
         lambda: attrs(dh, PIPELINE_MODES=("off", "post", "full", "вкл")),
         [("test_docling_pipeline", "test_three_modes_not_two"),
          ("test_docling_pipeline", "test_unknown_mode_dies_loudly")]),

        ("перевод ярлыков угадывается правилом «чего не знаю — то текст»",
         lambda: attrs(dh, EGRET_TO_DOCLING=GuessingTranslation(
             dh.EGRET_TO_DOCLING)),
         [("test_docling_pipeline", "test_unknown_label_dies_at_construction")],
         "no_docling_package"),

        ("витринное имя egret осталось непереведённым",
         lambda: attrs(dh, EGRET_TO_DOCLING=egret_without_translation()),
         [("test_docling_pipeline", "test_egret_names_translate_whole"),
          ("test_docling_pipeline",
           "test_translation_covers_both_dictionaries")],
         "no_docling_package"),

        ("словарь политики egret потерял класс",
         lambda: attrs(policy, DOCLING_EGRET=docling_egret_short()),
         [("test_docling_pipeline",
           "test_translation_covers_both_dictionaries")]),

        ("политика прощает незнакомый ярлык",
         lambda: attrs(policy, check=check_that_forgives),
         [("test_policy", "test_unknown_label_raises"),
          ("test_policy", "test_label_missing_from_model_also_raises"),
          ("test_policy", "test_unknown_policy_name_raises"),
          ("test_policy", "test_check_does_not_use_the_union")]),

        ("политика сверяется с объединением словарей",
         lambda: attrs(policy, check=check_against_the_union),
         [("test_policy", "test_check_passes_on_its_own_dictionary")]),

        ("разряд угадывается для неизвестного ярлыка",
         lambda: attrs(policy, ROLE=GuessingRole(policy.ROLE)),
         [("test_policy", "test_role_raises_on_unknown")]),

        ("разрядов стало два вместо трёх",
         lambda: attrs(policy, ROLES=("text", "artifact")),
         [("test_policy", "test_every_label_has_one_of_three_roles")]),

        ("в объединении у table другой разряд",
         lambda: attrs(policy, ROLE=flipped_role()),
         [("test_policy", "test_union_agrees_with_every_dictionary"),
          ("test_policy", "test_artefacts_are_not_empty_and_are_artefacts")]),

        ("два словаря политики совпали",
         lambda: attrs(policy, POLICIES=duplicated_policy()),
         [("test_policy", "test_for_labels_picks_by_dictionary_not_by_name")]),

        ("адаптер объявил чужую политику",
         lambda: attrs(dh.DoclingHeron, policy_name="DocLayNet"),
         [("test_policy", "test_adapters_and_policies_agree")]),

        ("слепок политики несёт только артефакты",
         lambda: attrs(policy, snapshot=snapshot_only_artefacts),
         [("test_policy", "test_snapshot_carries_whole_dictionary")]),

        ("span берёт первую метку (прежняя редакция)",
         lambda: attrs(swap, span=span_takes_the_first),
         [("test_swap", "test_double_anchor_is_loud"),
          ("test_swap", "test_inverted_anchor_is_loud"),
          ("test_swap", "test_missing_anchor_is_loud"),
          ("test_swap", "test_crossed_anchors_are_loud")]),

        ("span не ловит перекрёста меток",
         lambda: attrs(swap, span=span_without_crossing),
         [("test_swap", "test_crossed_anchors_are_loud")]),

        ("span считает вложение перекрёстом",
         lambda: attrs(swap, span=span_calls_nesting_a_crossing),
         [("test_swap", "test_nested_anchors_are_not_a_crossing")]),

        ("метка узнаётся по префиксу, а не поимённо",
         lambda: attrs(swap, marks=marks_by_prefix),
         [("test_swap", "test_wrap_and_get_are_inverse"),
          ("test_swap", "test_broken_markup_from_the_model_goes_in_as_is"),
          ("test_swap", "test_swap_leaves_the_neighbour_byte_for_byte"),
          ("test_swap", "test_nested_anchors_are_not_a_crossing")]),

        ("swap не возвращает снятое — откат невозможен",
         lambda: attrs(swap, swap=swap_forgets_what_it_removed),
         [("test_swap",
           "test_swap_returns_what_it_removed_and_restore_puts_it_back")]),

        ("порядок якорей отсортирован",
         lambda: attrs(swap, anchors=anchors_sorted),
         [("test_swap", "test_anchors_keep_document_order")]),

        ("оборванная метка молча даёт пустой список",
         lambda: attrs(swap, anchors=anchors_swallow_unterminated),
         [("test_swap", "test_unterminated_mark_is_loud")]),

        ("реестр отдаёт пустую строку вместо падения",
         lambda: attrs(knobs, knob=knob_returns_empty),
         [("test_knobs", "test_unknown_knob_raises_not_returns_empty")]),

        ("пустая строка снаружи проигрывает умолчанию",
         lambda: attrs(knobs, knob=knob_ignores_empty),
         [("test_knobs", "test_snapshot_tells_set_from_default")]),

        ("слепок пропускает ручки-долги",
         lambda: attrs(knobs, snapshot=snapshot_skips_debts),
         [("test_knobs", "test_snapshot_holds_every_knob_with_every_field")]),

        ("на машину уезжают и умолчания",
         lambda: attrs(knobs, passthrough=passthrough_with_defaults),
         [("test_knobs", "test_passthrough_carries_only_what_was_set")]),

        ("в реестре ручка без потребителя",
         lambda: attrs(knobs, KNOBS=knobs_with_phantom()),
         [("test_knobs", "test_audit_finds_no_disagreement"),
          ("test_knobs", "test_readers_finds_consumers_and_counts_them")]),

        ("имя ручки задвоено",
         lambda: attrs(knobs, KNOBS=knobs_with_duplicate()),
         [("test_knobs", "test_names_are_unique")]),

        ("умолчание ручки не строка",
         lambda: attrs(knobs, KNOBS=knobs_with_int_default()),
         [("test_knobs", "test_defaults_are_strings")]),

        ("адаптер не объявил ручку, которую читает",
         lambda: attrs(dh.DoclingHeron,
                       knobs_read=lambda self: ("LAYOUT_SCORE_THRESHOLD",)),
         [("test_knobs", "test_adapters_declare_the_knobs_they_read")]),

        ("ручка off не дошла до адаптера — конвейер построен всё равно",
         lambda: attrs(knobs, knob=knob_says_post),
         [("test_docling_pipeline", "test_adapter_at_off_builds_no_pipeline")],
         "slow_only"),

        # ---- second level --------------------------------------------
        ("маршрут выводится из разряда, а не объявляется",
         lambda: attrs(PaddleOcrVl, routes=routes_guess_by_role),
         [("test_read", "test_kind_comes_from_the_prompt_not_from_the_answer"),
          ("test_read", "test_silence_carries_a_reason")]),

        ("cover прощает ярлык без маршрута",
         lambda: attrs(Reader, cover=cover_forgives),
         [("test_read", "test_unknown_label_is_loud")]),

        ("маршрут не сверяет ни вид, ни причину молчания",
         lambda: attrs(Route, check=route_check_forgives),
         [("test_read", "test_route_with_unknown_kind_is_loud")]),

        ("прибор чтения снова слепнет на OTSL",
         lambda: attrs(booktext, _answer_grid=grid_only_from_html),
         [("test_read", "test_otsl_grid_matches_html_grid_cell_for_cell"),
          ("test_text",
           "test_table_in_otsl_scores_like_the_same_table_in_html")]),

        ("отказ доставки записывается молчанием модели",
         lambda: attrs(vhttp.Http, send=refusal_looks_like_silence),
         [("test_read", "test_delivery_refusal_does_not_look_like_silence"),
          ("test_read", "test_delivery_refusal_is_a_value_not_a_throw")]),

        ("проверка адреса спрашивает «жив ли», а не «как тебя зовут»",
         lambda: attrs(vhttp.Http, check=transport_check_only_pings),
         [("test_read", "test_wrong_model_name_stops_the_run"),
          ("test_read", "test_transport_asks_who_is_answering")]),

        # A THIRD copy of the anchor rule turned up after two were fixed:
        # `doc/apply.from_read` grew its own the day `feed.py` was folded into
        # `html.anchor_of`. A copy appears not from malice but because
        # `f"p{i:04d}-b{j}"` is shorter than an import.
        ("doc/apply завёл свою копию правила якоря",
         lambda: attrs(ap, anchor_of=anchor_of_a_private_copy),
         [("test_html_order", "test_the_anchor_rule_has_exactly_one_home")]),

        # --- input snapshot: "could not derive" is a quantity, not consent
        ("невыведенная форма отпечатка объявляется полной",
         lambda: attrs(replay, shape=shape_silent_about_underived),
         [("test_knobs",
           "test_shape_that_could_not_be_derived_is_loud_not_silent")]),

        ("разбор отпечатка ослеп на все адаптеры",
         lambda: attrs(replay, _returned=lambda *a, **k: set()),
         [("test_knobs", "test_derivable_shape_still_requires_every_value")]),

        # --- skipping: any runner must do
        ("пропуск выбирается по установленному, а не по бегуну",
         lambda: attrs(support, skip=skip_by_what_is_installed),
         [("test_knobs",
           "test_skip_under_our_runner_does_not_depend_on_pytest_being_installed")]),

        ("пропуск всегда наш — чужой бегун засчитает провал",
         lambda: attrs(support, skip=skip_always_ours),
         [("test_knobs", "test_skip_under_pytest_stays_a_pytest_skip")]),

        ("бегун не знает чужого пропуска",
         lambda: attrs(support, foreign_skip=lambda e: False),
         [("test_knobs",
           "test_runner_counts_a_foreign_skip_as_a_skip_and_survives")]),

        ("бегун считает пропуском ЛЮБОЕ BaseException",
         lambda: attrs(support, foreign_skip=lambda e: True),
         [("test_knobs", "test_runner_still_lets_a_real_interrupt_out")]),

        # --- the order the model did not give
        # An order the model did not give is not set at all, and boxes reach
        # the book in the order the graph handed them over.
        ("порядок, которого модель не дала, не задан вовсе",
         lambda: attrs(order, permutation=lambda labels, boxes, w, h, index,
                       vocab, which=None: list(range(len(boxes)))),
         [("test_order_contract",
           "test_no_rank_means_our_rule_not_the_order_of_the_graph")]),

        ("наше правило вытеснило ранг модели",
         lambda: attrs(doclayout, has_rank=lambda out: False),
         [("test_order_contract", "test_model_rank_still_wins_over_our_rule")]),

        # --- the ruler that judges the assembly order
        ("варианты сборки складываются раз и при умолчании",
         lambda: attrs(metrics, _order_variants=variants_built_once_at_defaults),
         [("test_order_contract",
           "test_floor_variant_is_a_floor_at_every_point_of_the_sweep")]),

        ("развёртка ужата до одной точки",
         lambda: attrs(metrics, COLUMN_SWEEP={"overlap": (0.50,)}),
         [("test_order_contract",
           "test_floor_built_at_defaults_would_not_be_a_floor")]),

        ("приговор считается по НЕпересобранным вариантам",
         lambda: attrs(metrics, column_jumps_ranking=ranking_without_rebuilding),
         [("test_order_contract",
           "test_ranking_rebuilds_the_variants_it_measures")]),

        ("своя резкость делится на ширину ЛИСТА, а не размещения",
         lambda: attrs(crop, native_dpi=native_dpi_by_the_sheet),
         [("test_html_order",
           "test_native_dpi_divides_by_the_placement_not_by_the_sheet")]),

        ("резкостью страницы объявляется любая картинка на ней",
         lambda: attrs(crop, native_dpi=native_dpi_takes_any_image),
         [("test_html_order",
           "test_native_dpi_says_nothing_when_there_is_nothing_to_say")]),

        # --- fitness by ink ---------------------------------------------
        ("нарезка рамок доверена numpy",
         lambda: attrs(fit, _clip=clip_that_trusts_numpy),
         [("test_fitness", "test_box_off_the_sheet_covers_nothing")]),

        ("пиксель под двумя рамками считается дважды",
         lambda: attrs(fit, _carried_as_text=carried_as_text_by_double_counting),
         [("test_fitness", "test_pixel_under_two_boxes_counts_once")]),

        ("отчёт прежней редакции: один порог, ни dpi, ни слова о слепоте",
         lambda: attrs(fit, report=report_of_the_previous_edition),
         [("test_fitness", "test_report_declares_the_whole_ruler"),
          ("test_fitness", "test_report_says_out_loud_that_it_is_blind_to_merging"),
          ("test_fitness", "test_blank_page_is_not_a_total_loss"),
          ("test_fitness", "test_truth_without_artefacts_is_not_a_missing_truth"),
          ("test_fitness", "test_object_without_ink_is_a_bench_defect_not_a_score")]),

        ("память растра чистится целиком при переполнении",
         lambda: attrs(fit, _ink_of=ink_memory_that_clears_itself),
         [("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # The memory remembers nothing. The price: 120 pages of the golden
        # bench render with the threshold in 33.4 s on an idle machine, 278 ms
        # a page; the battery calls `measure` 24 times over 23 raster passes,
        # so 600 pages mean 64 minutes of rendering against eight.
        ("память растра не помнит ничего",
         lambda: attrs(fit, _ink_of=lambda pdf, doc, i, dpi: fit._ink(doc[i], dpi)),
         [("test_fitness", "test_ink_memory_pays_nothing_twice_when_the_book_fits"),
          ("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # Evicting the oldest instead of holding what was gathered. A
        # separate mutation, not a variant of the one above: the byte cap and
        # the bit packing were in place and there was still no saving. Numbers
        # in `ink_memory_that_evicts_the_oldest`.
        ("память растра вытесняет старейшее",
         lambda: attrs(fit, _ink_of=ink_memory_that_evicts_the_oldest),
         [("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # Our own book is held and a foreign one is never evicted -- exactly
        # the old "hold what was gathered". One book does not suffer; a second
        # in the same process gets not a byte: 15600 renders against 3600 on
        # the real access trace.
        ("память растра не уступает места следующей книге",
         lambda: attrs(fit, _evict_foreign=lambda pdf: False),
         [("test_fitness", "test_ink_memory_makes_room_for_the_next_book")]),

        # A cap that does not hold the bench it was derived for: the bench is
        # 2998 MiB as booleans and 375 MiB packed, and 256 MiB held 362 pages
        # of 600.
        ("потолок памяти опущен ниже золотого стенда",
         lambda: attrs(fit, _INK_CACHE_MAX_BYTES=256 << 20),
         [("test_fitness", "test_the_cap_holds_the_bench_it_was_raised_for")]),

        # --- line-level: `attrs` cannot reach these places ------------------
        ("сторож молчания модели снят",
         lambda: one_line("booksmith.fitness",
                          "        if i not in M:\n"
                          "            raise metrics.MetricError(",
                          "        if i not in M:\n"
                          "            continue\n"
                          "        if False:\n"
                          "            raise metrics.MetricError("),
         [("test_fitness", "test_page_the_model_did_not_mark_is_loud")]),

        ("свесившаяся рамка отвергается целиком",
         lambda: one_line("booksmith.fitness",
                          "    x0, y0 = max(0, x0), max(0, y0)\n"
                          "    x1, y1 = min(w - 1, x1), min(h - 1, y1)",
                          "    if x0 < 0 or y0 < 0 or x1 > w - 1 or y1 > h - 1:\n"
                          "        return None"),
         [("test_fitness", "test_box_hanging_over_the_edge_is_cut_by_the_sheet")]),

        ("рамка, шире объекта в полтора раза, его не везёт",
         lambda: one_line("booksmith.fitness",
                          "                if one > best:",
                          "                if (x[2] - x[0]) > 1.5 * "
                          "(b['box'][2] - b['box'][0]):\n"
                          "                    continue\n"
                          "                if one > best:"),
         [("test_fitness",
           "test_merging_two_objects_into_one_box_does_not_lower_the_numbers"),
          ("test_fitness", "test_the_number_that_grows_when_boxes_merge")]),

        # The one number of the ruler that GROWS when boxes merge. Count it
        # per box instead of per object and it goes quiet: on bench/hard36
        # multi-object boxes are 33 against 35 when merged, the objects
        # themselves 309 against 385.
        ("«не в одиночку» считает рамки, а не объекты",
         lambda: one_line("booksmith.fitness",
                          '                res["arrived_with_company"] += k',
                          '                res["arrived_with_company"] += 1'),
         [("test_fitness", "test_the_number_that_grows_when_boxes_merge")]),

        ("порог чернил разошёлся с порогом стенда",
         lambda: attrs(fit, INK=fit.INK + 1),
         [("test_fitness", "test_the_ink_threshold_has_one_meaning_in_both_homes")]),

        ("порог чернил выпал из ключа памяти",
         lambda: attrs(fit, _ink_of=ink_memory_without_the_threshold),
         [("test_fitness", "test_ink_threshold_is_part_of_the_memory_key")]),

        ("итог батареи не считает непомеренное",
         lambda: attrs(fit, mutations=battery_summary_without_the_unmeasured),
         [("test_fitness", "test_battery_counts_what_it_could_not_measure")]),

        ("батарея портит только вывод модели",
         lambda: attrs(fit, mutations=battery_that_corrupts_only_the_model),
         [("test_fitness", "test_battery_corrupts_all_three_sides")]),

        # Back to `put` inside the loop: the book is re-read per replacement.
        ("пакетная замена читает книгу на каждый блок",
         lambda: one_line(
             "booksmith.doc.apply",
             "                html, entry, _ = put_into(",
             "                put(out_dir, anchor, body, source=src,\n"
             "                    log=lambda *a: None)\n"
             "                html, entry, _ = put_into("),
         [("test_apply", "test_bulk_reads_the_book_once_not_once_per_block")]),

        ("разряды блоков берутся по одному",
         lambda: one_line("booksmith.doc.apply",
                          "    roles = block_roles(out_dir)",
                          "    roles = {}"),
         [("test_apply", "test_bulk_reads_the_book_once_not_once_per_block")]),

        # --- rental deadlines: both caps rejected GOOD machines -----------
        # Back to counting "did exactly that many megabytes arrive": a
        # shortfall becomes a zero again, i.e. "we are slow" = "it is broken".
        ("зонд снова мерит размер, а не время",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return got * 8 / 1e6 / dt "
                          "if got >= 4 * 1024 * 1024 else 0.0"),
         [("test_rent_deadlines",
           "test_a_narrow_channel_is_measured_not_called_broken")]),

        ("зонд занижает скорость вдесятеро",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return got * 8 / 1e6 / dt / 10"),
         [("test_rent_deadlines",
           "test_a_broken_machine_still_gives_a_number_below_any_floor")]),

        # Back to comparing against the rejection floor: one knob pulls two
        # ways again, and loosening it unties the hands of the permanent list.
        ("вечный список снова решает по порогу отбраковки",
         lambda: one_line("booksmith.remote.runner",
                          "    if best_link < 3 * link:",
                          "    if ours < 2 * link:"),
         # This one only: the body mutation leaves the signature alone.
         [("test_rent_deadlines",
           "test_a_machine_is_blamed_only_with_a_witness")]),

        # The rejection floor returns to the guard's SIGNATURE: one knob
        # given two opposite jobs again.
        ("порог отбраковки вернулся в сторож вечного списка",
         lambda: one_line(
             "booksmith.remote.runner",
             "def blame_machine(offer: dict, reason: str, *, ours: float, "
             "link: float,",
             "def blame_machine(offer: dict, reason: str, *, ours: float, "
             "link: float, limit: float = 2.0,"),
         [("test_rent_deadlines",
           "test_the_verdict_cannot_depend_on_the_rejection_floor")]),

        ("свидетель для вечного списка больше не нужен",
         lambda: one_line("booksmith.remote.runner",
                          "    if best_link < 3 * link:",
                          "    if False:"),
         [("test_rent_deadlines",
           "test_a_machine_is_blamed_only_with_a_witness")]),

        ("мёртвая труба выдаётся за живой канал",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return max(got * 8 / 1e6 / dt, 0.5)"),
         [("test_rent_deadlines", "test_a_dead_channel_is_the_only_zero")]),

        ("подъём контейнера снова режется своим потолком",
         lambda: one_line(
             "booksmith.remote.runner",
             "    vast.wait_running(iid, timeout=max(30.0, "
             "t_end - time.time()))",
             "    vast.wait_running(iid, timeout=max(30.0, min(120.0, "
             "t_end - time.time())))"),
         [("test_rent_deadlines",
           "test_connect_gives_the_boot_the_whole_attempt")]),

        ("отступы уничтожения снова плоские",
         lambda: attrs(vastmod.Vast, RETRY_S=(4, 4, 4, 4, 4)),
         [("test_rent_deadlines",
           "test_destroy_backs_off_instead_of_hammering")]),

        ("ждём дольше, чем машина живёт сама",
         lambda: attrs(vastmod.Vast, RETRY_S=(4, 40, 400, 4000, 40000)),
         [("test_rent_deadlines",
           "test_destroy_backs_off_instead_of_hammering")]),

        ("отказ доступа зовётся отказом машины",
         lambda: one_line("booksmith.remote.vast",
                          '                we_are_refused = any(k in str(e) '
                          'for k in ("403", "429"))',
                          "                we_are_refused = False"),
         [("test_rent_deadlines",
           "test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine")]),

        # --- assembly order: one rule for the project ----------------------
        ("перевод ярлыков потерял одну политику",
         lambda: attrs(order, _LABELS={k: v for k, v in order._LABELS.items()
                                       if k != "DocLayNet"}),
         [("test_order", "test_every_dictionary_has_a_translation")]),

        ("перевод целит в ярлык, которого правила не знают",
         lambda: attrs(order, _LABELS=dict(
             order._LABELS,
             DocLayNet=dict(order._LABELS["DocLayNet"], Table="section_header"))),
         [("test_order", "test_translations_name_only_labels_the_rules_look_at")]),

        ("в ключе перевода опечатка — он не сработает никогда",
         lambda: attrs(order, _LABELS=dict(
             order._LABELS,
             DocLayNet={("Tabel" if k == "Table" else k): v
                        for k, v in order._LABELS["DocLayNet"].items()})),
         [("test_order", "test_translations_use_labels_that_exist")]),

        # The `ours` rule needs no labels at all; asking for a policy on its
        # behalf drops the run on a dictionary the rule never touches.
        ("правило ours требует описанной политики",
         lambda: one_line("booksmith.order",
                          '    if (which or rule()) == "ours":\n        return None',
                          "    pass"),
         [("test_order", "test_ours_needs_neither_labels_nor_docling")]),

        ("правила порядка теряют рамку, а не переставляют",
         lambda: one_line("booksmith.order",
                          "    out = [e.cid for e in _predictor()"
                          ".predict_reading_order(els)]",
                          "    out = [e.cid for e in _predictor()"
                          ".predict_reading_order(els)][:-1]"),
         [("test_order", "test_docling_returns_a_permutation_and_touches_no_box")]),

        ("незнакомое правило сборки принимается молча",
         lambda: one_line("booksmith.order", "    if v not in RULES:",
                          "    if False:"),
         [("test_order", "test_an_unknown_rule_dies_loudly")]),

        # A second copy of the rule inside an adapter -- exactly what ailed
        # `docling_heron`: it sorted by one key and declared another.
        ("адаптер снова сортирует своим ключом",
         lambda: source_swap("models/yolox_layout.py",
                             "        which = order.rule()",
                             "        kept.sort(key=lambda t: (t[2][1],"
                             " t[2][0]))\n        which = order.rule()"),
         [("test_order", "test_no_adapter_sorts_by_itself_any_more")]),

        # --- the instrument you look with: it had no checks at all -------
        # Hits the PLACE OF THE FIX in cli.py, not the parser. The first
        # edition called `detect.parse_pages` directly, past `cmd_overlay`:
        # reverting cli.py whole reddened NOT ONE check of 163.
        ("cmd_overlay зовёт свой разбор страниц вместо общего",
         lambda: one_line("booksmith.cli",
                          "only = detect.parse_pages(a.pages, total)",
                          'only = [int(x) for x in '
                          'a.pages.replace(",", " ").split()]'),
         [("test_overlay", "test_pages_are_counted_from_one_like_detect"),
          ("test_overlay", "test_a_page_out_of_the_book_is_loud")]),

        # The mirror side of the same guard: it fixed both, checked one.
        ("страница, которой нет у истины, пропускается молча",
         lambda: one_line("booksmith.overlay",
                          'counts["missing_in_truth"].append(i)',
                          "pass"),
         [("test_overlay",
           "test_a_page_missing_from_the_truth_is_named_too")]),

        ("лист кричит по ярлыку, а не по правилу метрики",
         lambda: one_line(
             "booksmith.overlay",
             '                (loud if kind == "spurious_box" '
             'else quiet).append(x)',
             '                loud.append(x)'),
         [("test_overlay",
           "test_the_sheet_shouts_at_exactly_what_the_number_calls_extra")]),

        ("смена ярлыка красится как лишняя рамка",
         lambda: attrs(overlay, LABEL=overlay.SPURIOUS),
         [("test_overlay",
           "test_a_changed_label_is_not_painted_like_an_extra_box")]),

        # --- yolox: the value that decides every coordinate ---------------
        ("фильтр ужатия снова литерал на месте",
         lambda: source_swap("models/yolox_layout.py",
                             "interpolation=INTERP", "interpolation=1"),
         [("test_yolox_fingerprint",
           "test_the_resize_filter_is_a_named_constant_not_a_literal")]),

        ("фильтр ужатия убран из отпечатка",
         lambda: source_swap("models/yolox_layout.py",
                             '"cv2_filter": INTERP', '"подложка2": PAD'),
         [("test_yolox_fingerprint",
           "test_the_fingerprint_declares_the_resize_filter")]),

        # --- a repeat may not grow the undo stack -------------------------
        # Remove it and a second `books apply` on the same book doubles the
        # journal without changing a character: 412 swaps become 824 and
        # `--undo` has to be called twice. The safety of the command's default
        # rests on exactly this.
        ("повтор замены снова растит стопку отката",
         lambda: one_line("booksmith.doc.apply",
                          "    if swap.get(html, anchor) == body:",
                          "    if False:"),
         [("test_apply", "test_putting_the_same_markup_twice_changes_nothing")]),

        # --- book order: the hole NOTHING caught --------------------------
        # A sceptic reversed the block walk with one line and the full battery
        # stayed green: 201 checks, 0 failures. The book would read backwards,
        # while all three instruments measure detection PAGES, not the
        # document.
        ("книга собирается в перевёрнутом порядке",
         lambda: one_line("booksmith.doc.html",
                          "        for b in page.blocks:",
                          "        for b in reversed(page.blocks):"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # The guard is EASY to make tautological, and the first edition was:
        # the expectation was gathered inside the very loop it guards. Three
        # mutations, none caught. The check's AST parse demands it live
        # outside.
        ("ожидание порядка снова копится внутри цикла",
         lambda: one_line("booksmith.doc.html",
                          "        expected.extend(anchor_of(page.index, b.block_id) for b in page.blocks)",
                          "        pass"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # The guard inside the builder: the check compares the order itself,
        # so it notices the removal only by PARSING THE SOURCE -- hence
        # `sources`, not `one_line`. Third mistake in a row on this: a
        # mutation's mechanism decides as much as the damage does.
        ("сборщик перестал сверять порядок книги",
         lambda: sources("doc/html.py",
                         "    if got != expected:",
                         "    if False:"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # Three places where moving the kitchen into `assets/` broke working
        # code, and all three were found by cross-checking, not by reading.
        ("журнал прежней раскладки снова невидим",
         lambda: one_line("booksmith.doc.apply",
                          '        old = os.path.join(out_dir, "swaps.json")',
                          '        old = os.path.join(out_dir, "absent.json")'),
         [("test_apply",
           "test_a_journal_from_the_old_layout_is_seen_not_declared_empty")]),

        ("сборщик снова не узнаёт свой каталог по слепку в кухне",
         lambda: one_line("booksmith.doc.html",
                          '    return (os.path.exists(os.path.join(out_dir, ASSETS, "run.json"))',
                          '    return (False'),
         [("test_html_order", "test_the_builder_recognises_its_own_directory")]),

        ("слепок снова ищется только в корне",
         lambda: one_line("booksmith.run.replay",
                          '              os.path.join(outdir, ASSETS, "run.json")):',
                          '              ):'),
         [("test_knobs", "test_replay_finds_the_snapshot_in_both_layouts")]),

        # The source inside the book is the only thing that survives a move.
        # Drop its priority and `books apply` on a copied book follows the
        # absolute path from the snapshot, which the new machine does not have.
        ("источник внутри книги перестал быть главнее пути из слепка",
         lambda: one_line("booksmith.doc.apply",
                          '    if os.path.isdir(os.path.join(own, "pages")):',
                          "    if False:"),
         [("test_apply",
           "test_the_source_inside_the_book_beats_the_recorded_path")]),

        # The book remembers what it was built from: without that `books
        # apply` with no flags would not know what to place, and the default
        # would have to go.
        ("книга перестала помнить свой источник",
         lambda: one_line("booksmith.doc.apply",
                          '    path = ((snapshot.get("args") or {}).get("detect") or "").strip()',
                          '    path = ""'),
         [("test_apply", "test_the_book_remembers_where_it_was_built_from")]),

        # --- the book must carry itself -----------------------------------
        # Knob defaults are what the reader gets. Put them back into
        # neighbouring-file mode and a book opened over a network path shows
        # raw LaTeX instead of formulas, saying nothing.
        ("умолчание HTML_MATH снова ссылается на соседний файл",
         # `one_line`, NOT `sources`: the check RUNS the builder, which asks
         # the imported module for the default. Swapping the file on disk
         # never reaches it -- on the first run the mutation came out "NOT
         # CAUGHT" for exactly that reason.
         lambda: one_line("booksmith.run.knobs",
                          'Knob("HTML_MATH", "inline",',
                          'Knob("HTML_MATH", "local",'),
         [("test_html_order",
           "test_the_book_is_alone_at_the_root_and_carries_itself")]),

        # --- shell defaults against the registry --------------------------
        # The promise in `run.sh` ("tests/test_knobs.py will catch a drift")
        # lived as one line of prose: there was no check at all. This breaks a
        # default in the script that ships to the rented card.
        ("умолчание в run.sh разошлось с реестром",
         lambda: sources("models/paddleocr_vl/run.sh",
                         "${PORT:-8118}", "${PORT:-9999}"),
         [("test_knobs", "test_shell_defaults_agree_with_the_registry")]),

        # --- the grid round trip may not lose content ---------------------
        # Without escaping, the cell `a<b&c` comes back as `a`, and the
        # corruption battery measures a truncated string while reporting the
        # whole one.
        ("ячейка таблицы снова не экранируется",
         lambda: one_line("booksmith.text",
                          '            out.append("<td>" + _html.escape('
                          'g.get((r, c), "")) + "</td>")',
                          '            out.append("<td>" + g.get((r, c), "")'
                          ' + "</td>")'),
         [("test_text",
           "test_a_cell_with_angle_brackets_survives_the_round_trip")]),

        # --- the ruler measures THE SAME rule the book is built with ------
        # A second copy of the "ours" rule lived in `metrics._by_reading`, keys
        # matching by luck, `metrics` importing `order` not at all -- and the
        # project's main conclusion was drawn on this builder (2471 jumps
        # against 501 and 439).
        ("прибор снова сортирует своей копией правила",
         lambda: sources("metrics.py",
                         '        idx = order.permutation(',
                         '        idx = _naive_reading_order('),
         [("test_order",
           "test_the_ruler_measures_the_same_rule_the_book_is_built_with")]),

        # --- the money path: the pulse of an abandoned machine ------------
        # Whoever started the pulse stops it on failure. Remove this and the
        # abandoned machine is immortal: our own thread keeps knocking `touch
        # /root/.alive`, and the dead-man's watch on the card depends on
        # neither our key nor our process.
        ("пульс не гасится, когда связь оборвалась после него",
         lambda: one_line("booksmith.remote.runner",
                          "            box.stop_heartbeat()",
                          "            pass"),
         [("test_rent_deadlines",
           "test_a_failed_connect_leaves_no_machine_with_a_live_pulse")]),

        # --- two copies of the `--pages` parser: at home and on the card --
        # They cannot be merged: four files ship to the box, no package there.
        # So their agreement is guarded instead. Before the guard they
        # disagreed on four inputs of thirteen, and the string is parsed ON THE
        # CARD, where a bare traceback means a rental paid for nothing.
        ("пробел перестал разделять страницы в копии для карты",
         lambda: sources("models/dots_ocr/entrypoint.py",
                         'str(spec).replace(" ", ",").split(",")',
                         'str(spec).split(",")'),
         [("test_parse_pages", "test_both_copies_of_parse_pages_agree"),
          ("test_parse_pages", "test_a_space_separates_pages_in_both_copies")]),

        ("дефис на карте перестал значить «вся книга»",
         lambda: sources("models/dots_ocr/entrypoint.py",
                         'if not spec or spec == "-":',
                         'if not spec:'),
         [("test_parse_pages",
           "test_the_dash_means_the_whole_book_only_on_the_box")]),

        # Back to a hard-coded value: the snapshot answers "no drift" while
        # the guard beside it says otherwise. Without this the fix rested on
        # nothing -- the field IS in the snapshot, and `replay --check`
        # approves it, comparing keys and not values.
        ("расхождение порога снова зашито литералом",
         lambda: source_swap("models/yolox_layout.py",
                             '"threshold_drift": self.threshold_drift()',
                             '"threshold_drift": []'),
         [("test_yolox_fingerprint",
           "test_the_fingerprint_asks_the_threshold_guard_instead_of_a_literal"
           )]),

        ("--pages overlay считается с нуля, а detect — с единицы",
         lambda: one_line("booksmith.detect",
                          "return [p - 1 for p in sorted(set(want))]",
                          "return sorted(set(want))"),
         [("test_overlay", "test_pages_are_counted_from_one_like_detect")]),

        ("страница, которой нет у модели, пропускается молча",
         lambda: one_line("booksmith.overlay",
                          'counts["missing_in_model"].append(i)',
                          "pass"),
         [("test_overlay", "test_a_page_missing_from_one_markup_is_named")]),

        ("итог называет страницы книги, а не нарисованные листы",
         lambda: one_line(
             "booksmith.overlay",
             'log(f"{out}: листов нарисовано {sheets} из {n} в книге, '
             'рамок {drawn}")',
             'log(f"{out}: листов нарисовано {n} из {n} в книге, '
             'рамок {drawn}")'),
         # This one only: `test_pages_are_counted…` now counts boxes via
         # `get_drawings()` in the output PDF and no longer depends on the
         # summary line -- it looks at what is DRAWN, not at what is said.
         [("test_overlay",
           "test_the_summary_counts_sheets_not_pages_of_the_book")]),

        ("одна разметка отчитывается тремя нулями",
         lambda: one_line(
             "booksmith.overlay",
             'log(f"  одна разметка «{sets[0][1]}»: сличать эти {drawn} рамок НЕ "',
             'log(f"  совпало 0, НЕ НАШЛА 0, ЛИШНИХ 0 «{sets[0][1]}» {drawn} "'),
         [("test_overlay",
           "test_one_markup_says_there_is_nothing_to_compare")]),

        ("несверенная разметка не называется",
         lambda: one_line("booksmith.overlay", "unchecked.append(tag)", "pass"),
         [("test_overlay", "test_what_was_not_checked_by_sha256_is_named")]),

        # --- the golden bench: a builder that had not one check -----------
        ("порядок классов принимается на веру",
         lambda: attrs(annopage, _yaml_names=lambda root: None),
         [("test_annopage",
           "test_class_order_is_checked_against_the_second_source")]),

        # The truth is written straight into place again.
        ("истина пишется на место, до сторожей",
         lambda: one_line("booksmith.annopage",
                          'work = tdir + ".новая"',
                          'work = tdir'),
         [("test_annopage",
           "test_a_failed_build_does_not_destroy_good_truth")]),

        # The sheet scale is a number again, not the knob.
        ("размер листа стенда зашит, а не взят из PAGE_DPI",
         lambda: one_line("booksmith.annopage",
                          "page = doc.new_page(width=w * scale, "
                          "height=h * scale)",
                          "page = doc.new_page(width=w * 0.5, height=h * 0.5)"),
         [("test_annopage", "test_the_sheet_follows_the_declared_knob")]),

        # --- splitting spreads: the veto was broken IN BOTH DIRECTIONS ----
        ("вето смотрит всю пробу, вместе с кромкой скана",
         lambda: attrs(djvu, gutter_rule=veto_looks_at_the_whole_probe),
         [("test_djvu", "test_scan_edge_at_the_top_does_not_veto"),
          ("test_djvu", "test_scan_edge_at_the_bottom_does_not_veto"),
          ("test_djvu", "test_veto_does_not_depend_on_the_height_of_the_scan"),
          ("test_djvu", "test_the_probe_selfcheck_agrees_with_the_veto")]),

        ("приграничная полоса съедает тело листа",
         lambda: attrs(djvu, RULE_EDGE=0.06),
         [("test_djvu", "test_rule_near_the_edge_of_the_body_still_vetoes")]),

        ("вето мерит долю сквозных строк, а не длину линейки",
         lambda: attrs(djvu, gutter_rule=veto_measures_the_share_of_rows),
         [("test_djvu", "test_hairline_rule_of_a_single_probe_row_vetoes"),
          ("test_djvu", "test_rule_across_the_gutter_vetoes"),
          ("test_djvu", "test_veto_does_not_depend_on_the_height_of_the_scan")]),

        # The probe knob: the only mutation here aimed at the veto's
        # RESOLUTION rather than its construction. The other djvu checks are
        # deliberately indifferent to `PROBE_DPI`, so without this the knob
        # could go back to 36 with a green battery -- killing three real tables
        # through the gutter.
        ("проба огрублена до прежних 36 dpi",
         lambda: attrs(djvu, PROBE_DPI=36),
         [("test_djvu",
           "test_a_thin_rule_across_the_gutter_needs_the_probe_we_declared")]),

        ("линейкой считается любая чернота через корешок",
         lambda: attrs(djvu, RULE_RUN=0.05),
         [("test_djvu", "test_binding_shadow_in_the_body_does_not_veto")]),

        ("порог длины задран выше любой линейки",
         lambda: attrs(djvu, RULE_RUN=0.9),
         [("test_djvu", "test_rule_across_the_gutter_vetoes"),
          ("test_djvu", "test_hairline_rule_of_a_single_probe_row_vetoes"),
          ("test_djvu", "test_rule_near_the_edge_of_the_body_still_vetoes")]),

        ("живая ручка помечена долгом",
         lambda: attrs(knobs.KNOB["DOCLING_PIPELINE"], debt=True),
         [("test_knobs", "test_docling_pipeline_is_registered")]),

        # ---- second level: transport ----------------------------------
        ("пустой ответ переспрашивается",
         lambda: attrs(vhttp.Http, send=send_asks_again_on_silence),
         [("test_read", "test_answer_200_is_never_repeated")]),

        ("повторы поняты как попытки — промах на единицу",
         lambda: attrs(vhttp.Http, __init__=http_takes_retries_for_attempts),
         [("test_read", "test_delivery_refusal_is_repeated")]),

        ("сторож пустой вырезки снят",
         lambda: attrs(vhttp, _data_uri=data_uri_without_the_empty_guard),
         [("test_read", "test_empty_crop_is_loud")]),

        ("вырезка ужимается перед отправкой",
         lambda: attrs(vhttp, _data_uri=data_uri_shrinks_the_crop),
         [("test_read", "test_the_very_crop_reaches_the_model")]),

        # ---- second level: recording the answer -----------------------
        ("запись ответа не несёт, чем кончилось порождение",
         lambda: attrs(Said, to_json=said_json_without_finish),
         [("test_read", "test_five_zeroes_are_counted_apart")]),

        ("байты модели подчищены пробелами",
         lambda: attrs(Said, to_json=said_json_strips_the_text),
         [("test_read", "test_model_bytes_are_untouched")]),

        ("догадка о виде дописана в текст блока",
         lambda: attrs(Said, to_json=said_json_writes_the_guess_into_the_text),
         [("test_read", "test_observed_lives_beside_not_inside")]),

        # ---- second level: the book pass ------------------------------
        ("рисунки тоже спрашиваем",
         lambda: attrs(PaddleOcrVl, routes=routes_read_the_pictures_too),
         [("test_read", "test_read_fills_content_in_the_same_page_schema")]),

        ("в отпечаток чтеца дописан адрес",
         lambda: attrs(PaddleOcrVl,
                       fingerprint=reader_fingerprint_with_the_address),
         [("test_read", "test_resume_does_not_ask_twice")]),

        ("отпечаток чтеца больше не несёт промтов",
         lambda: attrs(PaddleOcrVl,
                       fingerprint=reader_fingerprint_without_prompts),
         [("test_read", "test_snapshot_carries_prompts_and_our_parser")]),

        ("слепок детекции пересчитывает sha256 книги под текущий файл",
         lambda: attrs(vrun, _detect_facts=detect_facts_refresh_the_hash),
         [("test_read", "test_swapped_pdf_stops_the_run")]),

        ("ноль страниц к чтению — просто пустой итог",
         lambda: attrs(vrun, read_book=read_book_shrugs_at_zero_pages),
         [("test_read", "test_empty_run_is_not_a_success")]),

        # ---- second level: routes and kinds ---------------------------
        ("в словаре детектора класс, которому не завели маршрут",
         lambda: attrs(policy, POLICIES=policies_with_a_new_class()),
         [("test_read", "test_every_label_of_every_dictionary_has_a_route")]),

        ("книга разучилась принимать latex",
         lambda: attrs(ap, KINDS=("html", "otsl", "text")),
         [("test_read", "test_declared_kinds_agree_with_the_book")]),

        # ---- second level: parsing OTSL -------------------------------
        ("пустой ответ нюхается как текст",
         lambda: attrs(vrun, _sniff=sniff_calls_emptiness_text),
         [("test_read", "test_sniffed_kind_never_overrides_the_declared_one")]),

        ("рваность OTSL не считается (по-вендорски)",
         lambda: attrs(otsl, parse=parse_pads_like_the_vendor),
         [("test_read", "test_torn_otsl_is_counted_not_repaired")]),

        ("продолжение соседа заведено клеткой с собственным текстом",
         lambda: attrs(otsl, CONTENT=otsl.CONTENT + otsl.SPAN),
         [("test_read", "test_otsl_span_occupies_all_its_addresses")]),

        ("не-OTSL возвращается пустой сеткой вместо None",
         lambda: attrs(otsl, grid=grid_of_prose_is_an_empty_table),
         [("test_read", "test_not_otsl_is_none_not_empty")]),

        # ---- OTSL into HTML: this builds EVERY table of the book -------
        # The first of five is the one that used to pass unnoticed: replacing
        # the whole function with a stub failed none of 202 checks.
        ("перевод таблицы подменён заглушкой",
         lambda: attrs(otsl, to_html=to_html_is_a_stub),
         [("test_otsl_html", "test_declared_colspan_survives_the_translation"),
          ("test_otsl_html", "test_no_cell_disappears_in_translation"),
          ("test_otsl_html", "test_not_a_table_is_empty_string_not_a_"
                             "broken_tag")]),

        ("слияния разворачиваются в повторы (как было)",
         lambda: attrs(otsl, to_html=to_html_flattens_every_span),
         [("test_otsl_html", "test_declared_colspan_survives_the_translation"),
          ("test_otsl_html", "test_span_chain_resolves_to_the_root_not_to_"
                             "the_neighbour")]),

        ("слияние угадывается по совпадению текста соседей",
         lambda: attrs(otsl, to_html=to_html_merges_equal_neighbours),
         [("test_otsl_html", "test_equal_neighbours_without_a_tag_are_not_"
                             "merged")]),

        ("шапкой объявляется первая строка, а не метка модели",
         lambda: attrs(otsl, to_html=to_html_calls_the_first_row_a_header),
         [("test_otsl_html", "test_header_cells_come_from_the_model_"
                             "dictionary_not_from_the_row_number")]),

        ("строка получает <tr> только там, где есть корень",
         lambda: attrs(otsl, to_html=to_html_opens_a_row_only_where_a_root_is),
         [("test_otsl_html", "test_a_row_of_continuations_still_gets_its_row"),
          ("test_otsl_html", "test_an_empty_grid_row_is_not_swallowed")]),

        ("короткая строка добивается пустыми клетками",
         lambda: attrs(otsl, to_html=to_html_pads_short_rows),
         [("test_otsl_html", "test_a_short_row_is_not_padded_out")]),

        ("развёрнутому слиянию подставляется наш тег вместо тега корня",
         lambda: attrs(otsl, layout=layout_gives_the_split_span_our_default_tag),
         [("test_otsl_html", "test_a_split_span_keeps_one_tag_for_all_its_"
                             "addresses")]),

        ("рваное слияние выпрямляется молча (по-вендорски)",
         lambda: attrs(otsl, layout=layout_straightens_a_torn_span),
         [("test_otsl_html", "test_torn_span_is_left_flat_not_straightened")]),

        ("сквозная клетка перестала занимать все свои адреса",
         lambda: attrs(otsl, parse=parse_keeps_only_the_span_root),
         [("test_otsl_html", "test_parse_keeps_its_old_contract"),
          ("test_read", "test_otsl_span_occupies_all_its_addresses")]),

        ("layout завёл СВОЙ обход тегов, второй экземпляр правила",
         lambda: sources("otsl.py",
                         "    cells, own, tally = _walk(s)",
                         "    _ = _TOK.findall(s)\n"
                         "    cells, own, tally = _walk(s)"),
         [("test_otsl_html", "test_one_walk_serves_both_readers")]),

        # ---- truncation at the ceiling: the observed reaches the book --
        ("форма таблицы проверяется счётчиками рваности",
         lambda: attrs(dhtml, torn_grid=torn_grid_trusts_the_tearing_counters),
         [("test_torn", "test_torn_grid_catches_the_shape_no_tearing_"
                        "counter_can_see"),
          ("test_torn", "test_torn_grid_falls_on_deliberately_broken_input")]),

        ("любая однострочная сетка объявляется невозможной",
         lambda: attrs(dhtml,
                       torn_grid=torn_grid_calls_any_single_row_impossible),
         [("test_torn", "test_torn_grid_zero_from_absence_is_not_zero_"
                        "from_checking")]),

        ("битый файл answers/ уносит всё наблюдённое",
         lambda: attrs(dhtml, observed=observed_swallows_a_broken_answers_file),
         [("test_torn", "test_broken_answers_file_does_not_silently_"
                        "erase_the_others")]),

        ("отсутствие answers/ выдаётся за благополучие",
         lambda: attrs(dhtml,
                       observed=observed_invents_a_clean_bill_when_there_is_nothing),
         [("test_torn", "test_no_answers_is_silence_not_a_clean_bill")]),

        ("обёртка замены снимает пометку обрыва",
         lambda: attrs(ap, _wrap_fragment=wrap_fragment_drops_the_torn_mark),
         [("test_torn", "test_the_mark_survives_the_replacement")]),

        ("«не спрашивали» выдаётся за «оборвано»",
         lambda: attrs(ap, _wrap_fragment=wrap_fragment_marks_everything_torn),
         [("test_torn", "test_unknown_is_not_whole")]),

        ("from_read перестал спрашивать наблюдённое",
         lambda: sources("doc/apply.py",
                         "    obs = observed(read_dir)",
                         "    obs = {}"),
         [("test_torn", "test_from_read_asks_the_sidecar_for_the_reason")]),

        # ---- repeats within a page: proven, or merely nested ------------
        ("повтор сличается с самим собой",
         lambda: attrs(dhtml, repeats_on=repeats_compare_the_block_with_itself),
         [("test_repeat", "test_a_block_is_never_compared_with_itself")]),

        ("повтор сличается и с прочими кандидатами",
         lambda: attrs(dhtml,
                       repeats_on=repeats_compare_with_other_candidates_too),
         [("test_repeat", "test_two_equal_nested_blocks_are_not_hidden_"
                          "together")]),

        ("повтор не доказывается никогда",
         lambda: attrs(dhtml, repeats_on=repeats_never_prove_anything),
         [("test_repeat", "test_a_nested_block_found_in_a_remaining_one_"
                          "is_proven")]),

        ("повтором объявляется всё вложенное, без сличения",
         lambda: attrs(dhtml, repeats_on=repeats_prove_everything),
         [("test_repeat", "test_a_nested_block_whose_text_is_absent_is_"
                          "not_hidden")]),

        ("вложенный в артефакт судится наравне с текстовым",
         lambda: attrs(dhtml,
                       repeats_on=repeats_count_the_artefact_as_a_neighbour),
         [("test_repeat", "test_a_block_nested_in_an_artefact_is_not_a_"
                          "candidate")]),

        ("пустой блок берётся в кандидаты",
         lambda: attrs(dhtml, repeats_on=repeats_take_the_empty_block_too),
         [("test_repeat", "test_an_empty_block_is_not_a_candidate")]),

        ("остающиеся склеены без пробела — совпадение через шов",
         lambda: attrs(dhtml, repeats_on=repeats_join_without_a_gap),
         [("test_repeat", "test_a_match_across_the_seam_of_two_blocks_is_"
                          "not_evidence")]),

        ("у повтора снят порог длины",
         lambda: attrs(dhtml, repeats_on=repeats_have_no_length_floor),
         [("test_repeat", "test_a_two_character_match_is_not_evidence")]),

        ("свёрстанное прячется ради сырого латеха",
         lambda: attrs(dhtml, repeats_on=repeats_trade_typeset_for_raw),
         [("test_repeat", "test_the_typeset_form_is_not_traded_for_the_"
                          "raw_one")]),

        ("в ответе стоит объемлющая рамка, а не носитель",
         lambda: attrs(dhtml, repeats_on=repeats_name_the_enclosing_frame),
         [("test_repeat", "test_the_answer_names_the_carrier_not_the_"
                          "enclosing_frame")]),

        ("ступень латеха съедает имена команд",
         lambda: attrs(booktext, bare_math=bare_math_eats_the_command_name),
         [("test_repeat", "test_the_latex_stage_falls_on_deliberately_"
                          "broken_input"),
          ("test_repeat", "test_the_latex_stage_is_declared_with_its_"
                          "measurement")]),

        # --- the replacement quantities: guarded BY SHAPE ONLY -----------
        # Acceptance showed with seven mutations that the counters can be
        # broken without reddening one of 225 checks. Their seam is below.
        ("признак обрыва не доезжает до пакетной замены",
         lambda: attrs(ap, torn_of=lambda o: None),
         [("test_torn", "test_bulk_marks_the_torn_block_in_the_book")]),

        ("форма поставленного куска не судится",
         lambda: attrs(ap, torn_grid=shape_of_a_placed_block_is_never_asked),
         [("test_torn", "test_bulk_counts_the_impossible_shape_of_the_book_"
                        "not_of_the_run")]),

        # `one_line`, not `sources`: both of these were first written the
        # other way and ran for nothing.
        ("слияния в книге приравнены к объявленным",
         lambda: one_line(
             "booksmith.doc.apply",
             "    placed = sum(1 for c in cells if c[\"rows\"] > 1 "
             "or c[\"cols\"] > 1)",
             "    placed = announced"),
         [("test_torn", "test_bulk_counts_spans_declared_and_placed")]),

        ("переобёртка сверяется с ПЕРВОЙ ступенью стопки",
         lambda: one_line(
             "booksmith.doc.apply",
             "            if previous and previous[-1].get(\"sha256_model_answer\") == \\",
             "            if previous and previous[0].get(\"sha256_model_answer\") == \\"),
         [("test_torn", "test_bulk_names_the_rewrap_apart_from_new_work")]),

        ("отказанный блок считается лежащим в книге",
         lambda: one_line(
             "booksmith.doc.apply",
             "                tally[\"refused\"] += 1",
             "                _count_in_book(tally, misshapen, anchor, body,"
             " b.get(\"kind\") or \"html\"); tally[\"refused\"] += 1"),
         [("test_torn", "test_a_refused_block_is_not_counted_as_being_in_"
                        "the_book")]),

        ("причина пустоты сводится к «не прочитан»",
         lambda: attrs(dhtml, why_empty=why_empty_says_unread_for_everything),
         [("test_torn", "test_the_caption_names_which_zero_it_was")]),

        ("«не спрашивали» считается дочитанным",
         lambda: attrs(dhtml, torn_of=torn_of_calls_the_unasked_whole),
         [("test_torn", "test_the_torn_field_tells_three_states_apart")]),

        ("у правила столбца отнят порог",
         lambda: attrs(dhtml, torn_grid=torn_grid_column_rule_has_no_floor),
         [("test_torn", "test_torn_grid_zero_from_absence_is_not_zero_"
                        "from_checking")]),

        ("наблюдённое доезжает без причины остановки",
         lambda: attrs(dhtml,
                       observed=observed_keeps_anchors_and_drops_the_reason),
         [("test_torn", "test_observed_carries_the_reason_the_block_is_bad")]),

        # ---- the book: replacement, journal, anchor -------------------
        ("конец блока ищется по последней закрывающей метке",
         lambda: attrs(swap, span=span_ends_at_the_last_closing_mark),
         [("test_apply", "test_neighbour_is_untouched")]),

        ("status читает журнал и не открывает книгу",
         lambda: attrs(ap, status=status_reads_only_the_journal),
         [("test_apply", "test_status_tells_three_zeroes_apart")]),

        ("якорь сквозной, без номера страницы",
         lambda: attrs(dhtml, anchor_of=anchor_without_the_page),
         [("test_html_order", "test_anchor_is_page_scoped")]),

        # ---- the reading ruler: `books text` --------------------------
        ("блок без ответа получает CER 0",
         lambda: attrs(booktext, measure_pages=measure_scores_silence_as_zero),
         [("test_text", "test_silence_is_not_reported_as_perfect_reading")]),

        ("артефакт записан разрядом «текст»",
         lambda: attrs(booktext, measure_pages=measure_calls_artefacts_text),
         [("test_text",
           "test_perfect_reading_counts_only_text_in_the_text_line")]),

        ("в формуле считаются слова: запись артефакта несёт WER",
         lambda: attrs(booktext,
                       measure_pages=measure_counts_words_in_a_formula),
         [("test_text", "test_one_wrong_letter_in_a_formula_does_not_crash")]),

        ("молчание на артефакте засчитано ответом",
         lambda: attrs(booktext,
                       measure_pages=measure_counts_silence_as_an_answer),
         [("test_text", "test_silent_formulas_are_not_a_measured_one")]),

        ("знаковая истина артефакта снова не читается",
         lambda: attrs(booktext, _truth_text=truth_text_reads_only_tables),
         [("test_text", "test_artefact_with_truth_is_not_a_bait")]),

        ("нет истины — пустая строка",
         lambda: attrs(booktext, _truth_text=truth_text_empty_instead_of_none),
         [("test_text", "test_artefact_without_truth_stays_a_bait")]),

        ("счётчик выдумки на пустой истине снят",
         lambda: attrs(booktext,
                       measure_pages=measure_forgets_invention_on_empty_truth),
         [("test_text", "test_invention_on_declared_emptiness_is_counted")]),

        ("две истины на одном блоке выбираются молча",
         lambda: attrs(booktext, _truth_both=truth_both_chooses_silently),
         [("test_text", "test_two_truths_on_one_artefact_are_loud")]),

        # ---- the book: journal and comments ---------------------------
        ("сторож незакрытого комментария снят",
         lambda: attrs(ap, _check_comments=comments_guard_is_off),
         [("test_apply", "test_unclosed_comment_is_caught_by_its_own_guard")]),

        ("сторож комментариев запрещает их все",
         lambda: attrs(ap, _check_comments=comments_are_refused_wholesale),
         [("test_apply", "test_a_closed_comment_is_not_refused")]),

        ("нечитаемый журнал считается пустым",
         lambda: attrs(ap, load_journal=journal_unreadable_is_an_empty_one),
         [("test_apply", "test_a_broken_journal_is_not_an_empty_journal")]),

        ("журнал пишется прямо на своё место",
         lambda: attrs(ap, save_journal=journal_written_in_place),
         [("test_apply", "test_journal_is_written_atomically")]),

        # ---- the book: crops ------------------------------------------
        ("«срезано листом» значит «не осталось ничего»",
         lambda: attrs(crop, _clipped=clipped_only_when_nothing_is_left),
         [("test_html_order",
           "test_clipping_is_measured_with_a_tolerance_not_exactly")]),

        ("вырожденная рамка получает чужой диагноз",
         lambda: attrs(crop, cut=cut_without_the_named_troubles),
         [("test_html_order",
           "test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble")]),

        ("отрицательное поле зажато в ноль",
         lambda: attrs(crop, params=params_clamps_the_margin),
         [("test_html_order", "test_negative_margin_is_refused_out_loud")]),

        ("резкость вырезки берётся из окружения, а не у скана",
         lambda: attrs(crop, params=params_takes_the_dpi_from_the_environment),
         [("test_html_order",
           "test_crop_dpi_never_comes_from_the_environment_silently")]),

        # Three mutations on one rule, all three what a person really writes:
        # "take a bit more, the model will sort it out", "shrink the small ones
        # too", "the model's bounds are a detail".
        ("резкость вырезки тянется ВВЕРХ выше решётки скана",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_stretches_up),
         [("test_html_order",
           "test_crop_dpi_takes_the_ink_that_exists_and_invents_none")]),

        ("зажим считается по полной рамке, а режется пересечение",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_by_the_whole_box),
         [("test_html_order", "test_crop_dpi_counts_what_will_actually_be_cut")]),

        ("окно модели не спрашивается — режем как придётся",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_ignores_the_window),
         [("test_html_order",
           "test_crop_dpi_takes_the_ink_that_exists_and_invents_none")]),

        ("вложенность сравнивает голый ранг",
         lambda: attrs(dhtml, _nesting=nesting_compares_raw_order),
         [("test_html_order",
           "test_nesting_survives_blocks_without_a_model_rank")]),

        ("отказов листа три, а пометки две",
         lambda: attrs(dhtml, _sheet_trouble=sheet_trouble_with_two_marks),
         [("test_html_order",
           "test_three_kinds_of_bad_sheet_get_three_different_marks")]),

        ("doc/feed завёл свою копию правила якоря",
         lambda: attrs(feed, anchor_of=anchor_of_a_private_copy),
         [("test_html_order", "test_the_anchor_rule_has_exactly_one_home")]),

        ("the Cyrillic counter catches any non-ASCII",
         lambda: attrs(cyrmod, cyr=lambda s: sum(1 for c in s if ord(c) > 127)),
         [("test_cyrillic_ratchet",
           "test_the_counter_ignores_punctuation_it_must_not_chase")]),

        ("the Cyrillic counter counts lines, not codepoints",
         lambda: attrs(cyrmod, cyr=lambda s: len(s.splitlines())),
         [("test_cyrillic_ratchet",
           "test_the_counter_counts_codepoints_not_lines")]),

        ("book prose is no longer separated from ours",
         lambda: attrs(cyrmod, CONTENT_NAMES=()),
         [("test_cyrillic_ratchet",
           "test_book_content_is_exempt_by_name_not_by_file")]),

        ("the ratchet presses on book prose too",
         lambda: attrs(cyrmod, ratchet_areas=lambda c: dict(c)),
         [("test_cyrillic_ratchet",
           "test_book_content_is_exempt_by_name_not_by_file")]),

        ("the data walk does not descend",
         lambda: attrs(schema, _walk=_walk_top_only),
         [("test_data_contract",
           "test_the_guard_can_fail_when_the_data_renames"),
          ("test_data_contract",
           "test_every_declared_key_is_present_in_the_data")]),

        ("key floors are declared as zero",
         lambda: attrs(schema, FORMATS=_floors_zeroed()),
         [("test_data_contract", "test_the_floors_are_not_all_zero")]),

        ("the file pattern lost a directory level",
         lambda: attrs(schema, FORMATS=_globs_one_level_short()),
         [("test_data_contract",
           "test_the_declaration_reaches_the_files_it_names")]),

        ("the ratchet baseline is unreachable",
         lambda: attrs(cyrmod, BASELINE="/nonexistent/cyr-baseline.json"),
         [("test_cyrillic_ratchet",
           "test_the_baseline_exists_and_covers_every_area"),
          ("test_cyrillic_ratchet", "test_no_area_grew")]),

        ("the disk side of the presence guard goes quiet",
         lambda: attrs(schema, measure=_measure_finds_nothing),
         [("test_data_contract",
           "test_the_guard_can_fail_when_the_code_renames"),
          ("test_data_contract",
           "test_every_declared_key_is_present_in_the_data")]),

        ("the acceptance clock is not stripped",
         lambda: attrs(acceptance, _CLOCK=_clock_not_stripped()),
         [("test_acceptance", "test_score_on_annopage_reports_the_same_report"),
          ("test_acceptance", "test_score_on_hard_reports_the_same_report"),
          ("test_acceptance", "test_text_on_slovar_reports_the_same_report")]),

        ("the acceptance table no longer reads the data formats",
         lambda: attrs(acceptance, COMMANDS=_table_missing_a_format()),
         [("test_acceptance",
           "test_the_command_table_covers_every_format_the_migration_touches")]),

        ("only the cyrillic side of the prose is counted",
         lambda: attrs(cyrmod, latin=_latin_is_not_counted),
         [("test_cyrillic_ratchet",
           "test_the_counter_counts_codepoints_not_lines")]),

        ("the latin companion is not counted for finished files",
         lambda: attrs(cyrmod, latin=_counter_that_skips_finished_files),
         [("test_cyrillic_ratchet",
           "test_the_counter_counts_codepoints_not_lines")]),

        ("prose vanished without arriving in English",
         lambda: attrs(cyrmod, BASELINE=_baseline_of_deleted_prose()),
         [("test_cyrillic_ratchet",
           "test_prose_was_translated_not_deleted")]),

        ("book content is no longer weighed apart",
         lambda: attrs(cyrmod, CONTENT_NAMES=("PROSE_RU",)),
         [("test_cyrillic_ratchet", "test_book_content_did_not_move")]),

        ("an html attribute the code writes is not declared",
         lambda: attrs(schema, HTML_ATTRS=schema.HTML_ATTRS[1:]),
         [("test_data_contract",
           "test_the_code_emits_exactly_the_declared_html_attributes")]),

        ("the book is asked for an attribute it never carried",
         lambda: attrs(schema, HTML_CORE=schema.HTML_CORE + ("data-nonesuch",)),
         [("test_data_contract",
           "test_the_built_book_carries_the_declared_attributes")]),

        ("the help snapshot is taken from another command",
         lambda: attrs(acceptance, COMMANDS=dict(
             acceptance.COMMANDS, help=(["score", "--help"], []))),
         [("test_acceptance", "test_help_reports_the_same_text")]),

        ("the source hash is no longer normalised out of the report",
         lambda: attrs(acceptance, _TREE_HASH=_clock_not_stripped()),
         [("test_acceptance",
           "test_replay_check_reports_the_same_report")]),

        # --- the map against the tree -------------------------------------
        #
        # `README.md` once held a second copy of the code map and drifted from
        # the tree by eight modules and four commands within a month. The copy
        # went; the drift can still happen to the one that is left, and these
        # four say so out loud.

        ("the map is read from a file that is not the map",
         lambda: attrs(schema, DOC_MAP=os.path.join(
             os.path.dirname(schema.DOC_MAP), "README.md")),
         [("test_docs_map",
           "test_every_command_the_cli_declares_is_named_in_the_map")]),

        ("the map points at a file that is not there",
         lambda: attrs(schema, DOC_MAP=_map_naming_a_missing_file()),
         [("test_docs_map", "test_every_file_the_map_points_at_exists")]),

        ("the map offers a command the CLI does not have",
         lambda: attrs(schema, DOC_MAP=_map_naming_a_ghost_command()),
         [("test_docs_map",
           "test_the_map_names_no_command_that_does_not_exist")]),

        ("measurements are allowed back into the map",
         lambda: attrs(schema, DOC_MAP=_map_with_a_measurement()),
         [("test_docs_map",
           "test_the_map_does_not_grow_back_into_a_second_copy")]),

        ("the aging knob advertises a profile that does not exist",
         lambda: one_line("booksmith.run.knobs",
                          '    Knob("SYNTH_AGING", "old", "\u043f\u0440\u043e\u0444\u0438\u043b\u044c '
                          '\u0441\u0442\u0430\u0440\u0435\u043d\u0438\u044f \u0441\u0442\u0435\u043d\u0434\u0430: clean|scan|old|decayed"),',
                          '    Knob("SYNTH_AGING", "old", "profile: clean|scan|old|frail"),'),
         [("test_knobs",
           "test_the_aging_knob_lists_exactly_the_profiles_that_exist")]),

        ("the probe battery and the book drop out of the acceptance table",
         lambda: attrs(acceptance, COMMANDS={
             k: v for k, v in acceptance.COMMANDS.items()
             if k not in ("text-selfcheck", "apply-status")}),
         [("test_acceptance",
           "test_the_reading_probe_battery_reports_the_same"),
          ("test_acceptance", "test_the_built_book_reports_the_same_swaps")]),
    ]
    return [(t + ("",))[:4] if len(t) == 3 else t for t in m]


# --- running the battery ---------------------------------------------------

def fresh(name):
    """A fresh import of the check: its tables are built at import time."""
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


def reddens(mod_name, test_name):
    """Did the named check go red. A skip does NOT count as red."""
    mod = fresh(mod_name)
    fn = getattr(mod, test_name, None)
    if fn is None:
        return False, f"проверки {mod_name}::{test_name} больше нет"
    try:
        fn()
    except support.Skip as e:
        return False, f"пропущена ({e})"
    except (Exception, SystemExit) as e:
        return True, type(e).__name__
    return False, "прошла как ни в чём не бывало"


def all_tests():
    out = set()
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py"):
            mod = fresh(fn[:-3])
            for n in vars(mod):
                if n.startswith("test_") and callable(getattr(mod, n)):
                    out.add((fn[:-3], n))
    return out


def main():
    caught = missed = 0
    covered = set()
    skipped = []
    # WHICH CHECKS ARE RED WITH NO MUTATION AT ALL. Without this pass the
    # battery counts an already-failing check as caught by anything that names
    # it: `reddens` asks "did it go red under the mutation", not "did the
    # mutation make it go red". Measured: one self-failing check silently
    # certified the mutation "the ratchet baseline is unreachable" as caught,
    # having tested nothing.
    already_red = set()
    for mod_name, test_name in sorted({t for _, _, ts, _ in mutations() for t in ts}):
        red, _ = reddens(mod_name, test_name)
        if red:
            already_red.add((mod_name, test_name))
    for mod_name, _ in {t for _, _, ts, _ in mutations() for t in ts}:
        fresh(mod_name)
    if already_red:
        print("  RED WITH NO MUTATION (they count as caught by nothing): "
              + "; ".join(f"{m}::{t}" for m, t in sorted(already_red)))
    for name, broken, targets, needs in mutations():
        if needs and not NEEDS[needs]():
            skipped.append(f"{name} — {needs}")
            continue
        bad = []
        try:
            with broken():
                for mod_name, test_name in targets:
                    if (mod_name, test_name) in already_red:
                        bad.append(f"{mod_name}::{test_name} red without any mutation")
                        continue
                    red, why = reddens(mod_name, test_name)
                    if not red:
                        bad.append(f"{mod_name}::{test_name} {why}")
        finally:
            for mod_name, _ in targets:
                fresh(mod_name)          # back to undamaged code
        covered |= set(targets)
        if bad:
            missed += 1
            print(f"  НЕ ПОЙМАНА  {name}: " + "; ".join(bad))
        else:
            caught += 1
            print(f"  поймана     {name} ({len(targets)} проверки)")
    total = len(mutations())
    uncovered = sorted(all_tests() - covered)
    print(f"\nмутаций {total}: поймано {caught}, НЕ поймано {missed}, "
          f"пропущено {len(skipped)}")
    for s in skipped:
        print(f"  пропущена мутация: {s}")
    print(f"проверок под мутацией {len(covered)} из {len(all_tests())}; "
          f"без мутации {len(uncovered)}"
          + (": " + ", ".join(f"{m}::{t}" for m, t in uncovered)
             if uncovered else ""))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
    sys.exit(main())
