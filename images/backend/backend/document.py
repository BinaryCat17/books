import glob
import json
import os
import re
from dataclasses import asdict, dataclass

from backend import classes as policy
from backend import identity as stamp
from backend import job, textnorm
from backend.errors import Refusal
from backend.log import log
from backend.page import Page, anchor, write_json
from backend.store import KINDS


REPEAT_MIN = 3


def _union_area(holes):
    if not holes:
        return 0
    xs = sorted({v for h in holes for v in (h[0], h[2])})
    total = 0
    for a, b in zip(xs, xs[1:], strict=False):
        spans = sorted((h[1], h[3]) for h in holes if h[0] <= a and h[2] >= b)
        cov, end = (0, None)
        for y0, y1 in spans:
            if end is None or y0 > end:
                cov += y1 - y0
                end = y1
            elif y1 > end:
                cov += y1 - end
                end = y1
        total += cov * (b - a)
    return total


def why_empty(o: dict | None) -> str:
    if o is None:
        return "whether it was read: nothing to say -- no answers/ alongside"
    if o.get("error"):
        return f"there was no answer: {o['error']}"
    by_what = o.get("outcome")
    if by_what is None:
        return "never asked: the route is empty with a declared reason"
    if by_what == "length":
        return "the answer was cut off by the length ceiling"
    return "the model kept quiet: the answer came back empty"


def observed(detect_dir: str) -> dict:
    out = {}
    for fp in sorted(glob.glob(os.path.join(detect_dir, "answers", "*.json"))):
        try:
            with open(fp, encoding="utf-8") as f:
                recs = json.load(f).get("answers") or []
        except (ValueError, OSError, AttributeError):
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            a = r.get("anchor")
            if not a:
                continue
            side = r.get("observed") or {}
            out[a] = {
                "outcome": r.get("outcome"),
                "error": r.get("error"),
                "prompt": side.get("prompt"),
                "kind_promised": side.get("kind_promised"),
                "kind_sniffed": side.get("kind_sniffed"),
                "otsl_grid": side.get("otsl_grid"),
            }
    return out


def repeats_on(page, covered, pol=None) -> dict:
    pol = pol or policy.UNION
    from_text = [b for b in page.blocks if pol.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {
        b.block_id
        for b in from_text
        if any(o.block_id != b.block_id and covered(b.box, o.box) for o in from_text)
    }
    kept = [b for b in from_text if b.block_id not in nested]
    norm = {b.block_id: textnorm.normalize(b.content, "latex") for b in kept}
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        own = textnorm.normalize(b.content, "latex")
        carrier = next((o for o in kept if len(own) >= REPEAT_MIN and own in norm[o.block_id]), None)
        why = "differs"
        if carrier is not None:
            why = "layout" if _raw_latex_at(carrier.content, b.content) else "verbatim"
        out[b.block_id] = (carrier.block_id if carrier else None, why)
    return out


def _raw_latex_at(carrier: str, own: str) -> bool:
    math = ("\\[", "\\(", "$")
    if not any(m in own for m in math):
        return False
    if any(m in carrier for m in math):
        return False
    return bool(re.search("[_^]\\{|\\\\[a-zA-Z]+", carrier))


def torn_of(o: dict | None) -> bool | None:
    by_what = (o or {}).get("outcome")
    return None if by_what is None else by_what == "length"


def torn_grid(grid: dict | None) -> str | None:
    if not grid:
        return None
    rows, cells = (grid.get("rows") or 0, grid.get("grid_cells") or 0)
    if rows == 1 and cells > 3:
        return f"the whole table in one row: {cells} cells"
    if rows > 3 and cells == rows:
        return f"{rows} rows and only {cells} cells -- one per row"
    return None


def _union_share(boxes, sheet):
    if not boxes or sheet <= 0:
        return 0.0
    return min(1.0, _union_area([[float(v) for v in b] for b in boxes]) / sheet)


def _nesting(arts) -> dict:

    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    def rank(b):
        return (b.order is None, b.order or 0, b.block_id)

    inner = {}
    for b in arts:
        for o in arts:
            if o.block_id == b.block_id or not _covered(b.box, o.box):
                continue
            ab, ao = (area(b), area(o))
            if ab > ao * 1.02:
                continue
            if abs(ab - ao) <= ao * 0.02 and rank(o) >= rank(b):
                continue
            inner[b.block_id] = o.block_id
            break
    return inner


def _covered(inner, outer, part=0.9):
    x0, y0 = (max(inner[0], outer[0]), max(inner[1], outer[1]))
    x1, y1 = (min(inner[2], outer[2]), min(inner[3], outer[3]))
    i = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    a = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return a > 0 and i / a >= part


def _twice_area(boxes):
    if len(boxes) < 2:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0.0
    for a, c in zip(xs, xs[1:], strict=False):
        if c <= a:
            continue
        ev = []
        for b in boxes:
            if b[0] <= a and b[2] >= c and (b[3] > b[1]):
                ev.append((b[1], 1))
                ev.append((b[3], -1))
        ev.sort()
        cov, depth, prev = (0.0, 0, None)
        for y, d in ev:
            if depth >= 2:
                cov += y - prev
            depth += d
            prev = y
        total += cov * (c - a)
    return total


def _sheet_trouble(blocks, arts, pol=None) -> str | None:
    if not blocks:
        return "empty"
    if any((pol or policy.UNION).role(b.label) == "text" for b in blocks):
        return None
    return "no-text" if arts else "furniture-only"


def _order_src(page) -> str:
    m = page.meta or {}
    if "reading_order" not in m:
        return "not_said"
    v = m["reading_order"]
    if v is None:
        return "the field is there, the value is null"
    return v if isinstance(v, str) else f"not a string: {v!r}"


def _ours(v) -> bool:
    from backend.page import ours_order

    return ours_order(v)


@dataclass
class BlockData:
    anchor: str
    page: int
    block_id: int
    label: str
    cls: str
    role: str
    score: float | None
    order: int | None
    order_source: str
    content: str | None
    kind: str
    box: list
    reading: dict | None
    hit_ceiling: bool | None
    repeat_of: str | None
    repeat_verdict: str | None
    table_shape: str | None
    inside_artifacts: list | None
    inside: str | None
    contains: list | None
    nested_in_text: bool
    nested_in_text_strict: bool
    as_picture: bool
    why_empty: str | None


@dataclass
class PageData:
    index: int
    width: int
    height: int
    dpi: float
    order_source: str
    trouble: str | None
    image_share: float
    largest_artifact_share: float
    repeats_verbatim: int
    nested_artifacts: int
    blocks: list


@dataclass
class BookData:
    run_dir: str
    pdf: str
    page_dpi: float
    sha256: str | None
    sha256_said: str | None
    policy: policy.Policy
    observed: bool
    repeats_how: str
    snapshot: dict
    pages: list


def observed_page(detect_dir: str, index: int) -> dict:
    path = os.path.join(detect_dir, "answers", f"{anchor(index)}.json")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            recs = json.load(f).get("answers")
    except (ValueError, OSError, AttributeError):
        return out
    if not isinstance(recs, list):
        return out
    for r in recs:
        a = r.get("anchor")
        if not a:
            continue
        side = r.get("observed") or {}
        out[a] = {
            "outcome": r.get("outcome"),
            "error": r.get("error"),
            "prompt": side.get("prompt"),
            "kind_promised": side.get("kind_promised"),
            "kind_sniffed": side.get("kind_sniffed"),
            "otsl_grid": side.get("otsl_grid"),
        }
    return out


def answers_present(detect_dir: str) -> bool:
    d = os.path.join(detect_dir, "answers")
    return os.path.isdir(d) and any(n.endswith(".json") for n in os.listdir(d))


def _snapshot(detect_dir: str) -> dict:
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)


def _gather_page(page: Page, pol: policy.Policy, obs: dict, obs_present: bool) -> PageData:
    order_src = _order_src(page)
    arts = [b for b in page.blocks if pol.role(b.label) == "artifact"]
    repeats_page = repeats_on(page, _covered, pol)
    sheet = float(page.width) * float(page.height)
    share = _union_share([b.box for b in arts], sheet)
    trouble = _sheet_trouble(page.blocks, arts, pol)
    biggest = 0.0
    for b in arts:
        one = (b.box[2] - b.box[0]) * (b.box[3] - b.box[1]) / sheet if sheet else 0.0
        biggest = max(biggest, one)
    nested_in = _nesting(arts)
    verbatim = sum(1 for v in repeats_page.values() if v[1] == "verbatim")
    blocks = []
    for b in page.blocks:
        a = anchor(page.index, b.block_id)
        role = pol.role(b.label)
        inside = [o for o in arts if o.block_id != b.block_id and _covered(b.box, o.box)]
        outside = [
            o
            for o in page.blocks
            if o.block_id != b.block_id and pol.role(o.label) != "artifact" and _covered(b.box, o.box)
        ]
        in_text = role != "artifact" and bool(outside)
        strict = in_text and role == "text" and any(pol.role(o.label) == "text" for o in outside)
        repeat = repeat_text = None
        if b.block_id in repeats_page:
            owner_id, repeat_text = repeats_page[b.block_id]
            repeat = anchor(page.index, owner_id) if owner_id is not None else "page"
        o = obs.get(a) or {}
        outer = nested_in.get(b.block_id)
        outer_a = anchor(page.index, outer) if outer is not None else None
        as_picture = role == "artifact" or not (b.content or "").strip()
        blocks.append(
            BlockData(
                anchor=a,
                page=page.index,
                block_id=b.block_id,
                label=b.label,
                cls=pol.cls(b.label),
                role=role,
                score=b.score,
                order=b.order,
                order_source=order_src,
                content=b.content,
                kind=b.kind,
                box=list(b.box),
                reading=o or None,
                hit_ceiling=torn_of(o),
                repeat_of=repeat,
                repeat_verdict=repeat_text,
                table_shape=torn_grid(o.get("otsl_grid")),
                inside_artifacts=[anchor(page.index, x.block_id) for x in inside] or None,
                inside=outer_a,
                contains=[anchor(page.index, k) for k, v in nested_in.items() if v == b.block_id] or None,
                nested_in_text=in_text,
                nested_in_text_strict=strict,
                as_picture=as_picture,
                why_empty=why_empty(o if obs_present else None) if not b.content else None,
            )
        )
    return PageData(
        index=page.index,
        width=page.width,
        height=page.height,
        dpi=float(page.dpi),
        order_source=order_src,
        trouble=trouble,
        image_share=share,
        largest_artifact_share=biggest,
        repeats_verbatim=verbatim,
        nested_artifacts=len(nested_in),
        blocks=blocks,
    )


def gather_page(detect_dir: str, index: int) -> PageData:
    snap = _snapshot(detect_dir)
    pol = policy.Policy.from_snapshot(snap.get("policy"))
    path = os.path.join(detect_dir, "pages", f"{index:04d}.json")
    if not os.path.isfile(path):
        raise Refusal(f"no page {index} in {detect_dir}")
    with open(path, encoding="utf-8") as f:
        page = Page.from_json(json.load(f))
    return _gather_page(page, pol, observed_page(detect_dir, index), answers_present(detect_dir))


def gather(detect_dir: str, verify: bool = True) -> BookData:
    snap = _snapshot(detect_dir)
    pdf = snap["source"]["path"]
    page_dpi = float(snap["raster"]["dpi"])
    pol = policy.Policy.from_snapshot(snap.get("policy"))
    if not os.path.exists(pdf):
        raise Refusal(
            f"the parse source is not in place: {pdf}\nHTML is built from the PDF, not from the detection raster -- a crop of a dense table at {page_dpi:.0f} dpi is unreadable."
        )
    said = (snap.get("source") or {}).get("sha256")
    now = None
    if verify:
        now = stamp.sha256(pdf)
        if said and said != now:
            raise Refusal(
                f"{pdf} changed after detection: the snapshot swore sha256 {said[:12]}, now it is {now[:12]}. The crops would come from one file and the boxes from another. Recompute a detect run, or put back the PDF the boxes were counted on."
            )
        log(
            f"source {os.path.basename(pdf)} sha256 {now[:12]}"
            + (
                " -- matched the detection snapshot"
                if said
                else " -- the detection snapshot named no sha256, nothing to check against"
            )
        )
    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise Refusal(f"no pages in {detect_dir} -- run a detect run first")
    obs_present = answers_present(detect_dir)
    repeats_how = _repeats_how()
    pages = []
    for page_n, fp in enumerate(files, 1):
        job.current().check()
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(json.load(f))
        pages.append(_gather_page(page, pol, observed_page(detect_dir, page.index), obs_present))
        if page_n % 10 == 0 or page_n == len(files):
            log(f"  {page_n}/{len(files)} pages gathered", n=page_n, of=len(files))
    return BookData(
        run_dir=detect_dir,
        pdf=pdf,
        page_dpi=page_dpi,
        sha256=now,
        sha256_said=said,
        policy=pol,
        observed=obs_present,
        repeats_how=repeats_how,
        snapshot=snap,
        pages=pages,
    )


def _repeats_how() -> str:
    from backend import knobs

    how = (knobs.knob("HTML_REPEATS") or "hide").strip()
    if how not in ("hide", "show"):
        raise Refusal(
            f"HTML_REPEATS={how!r}: I know only hide | show. There is no silent default here: this is the one build operation that removes text from the reader's sight."
        )
    return how


VERSION = 1


def to_json(data: BookData) -> dict:
    kind = os.path.basename(os.path.dirname(data.run_dir))
    return {
        "version": VERSION,
        "run": {
            "kind": kind if kind in KINDS else "detect",
            "label": os.path.basename(data.run_dir),
            "identity": data.snapshot.get("identity"),
        },
        "source": {"name": os.path.basename(data.pdf), "sha256": data.sha256_said or data.sha256},
        "policy": data.policy.snapshot(),
        "page_dpi": data.page_dpi,
        "observed": data.observed,
        "pages": [asdict(p) for p in data.pages],
    }


def write(run_dir: str) -> dict:
    path = os.path.join(run_dir, "document.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        snap = _snapshot(run_dir)
        if (
            d.get("version") == VERSION
            and d["run"].get("identity") == snap.get("identity")
            and d["run"].get("when") == snap.get("when")
        ):
            return d
    d = to_json(gather(run_dir, verify=False))
    write_json(path, d)
    return d
