import dataclasses
import functools
import json
import os
import re
import shutil
from collections.abc import Iterator, Mapping
from backend import classes, raster
from backend import store as book
from backend import job
from backend import knobs
from backend import identity as stamp
from backend.errors import Refusal
from backend.log import log
from backend import corrections as corr
from backend import document, export as export_mod, fleet, measure, settings, truth
from backend import protocol as served


def admin() -> str:
    return settings.home()


def check_entries(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise Refusal("the registry is a mapping of names to entries")
    for name, e in raw.items():
        if not isinstance(e, dict):
            raise Refusal(f"{name}: an entry is a mapping")
        if e.get("kind") not in served.KINDS:
            raise Refusal(f"{name}: kind {e.get('kind')!r} is not one of {served.KINDS}")
        unknown = sorted(set(e.get("knobs") or {}) - set(knobs.names()))
        if unknown:
            raise Refusal(f"{name}: knobs nothing declares: {unknown}")
    return raw


def models() -> dict:
    return fleet.models()


def write_models(raw: object) -> dict:
    return fleet.write_models(check_entries(raw))


def _endpoint(e: dict, model: str, base: job.Job) -> tuple[str, str]:
    if e.get("endpoint"):
        return str(e["endpoint"]), str(e.get("api_key") or "")
    while True:
        got = fleet.lease(model, base.name or "adhoc")
        if got["state"] == "ready":
            return str(got["endpoint"]), str(got.get("key") or "")
        base.check()
        base.sink({"text": f"waiting for the model {model} to start (placement {got.get('placement')})"})


def _admin(store: str) -> bool:
    return os.path.realpath(store) == os.path.realpath(admin())


def _entry(model: str, presets: Mapping) -> dict:
    if model not in presets:
        raise Refusal(f"no model {model!r} in the registry; there are {sorted(presets) or 'none'}")
    return dict(presets[model])


def check(store: str, settings_: Mapping, presets: Mapping | None = None, model: str = "") -> None:
    if _admin(store) or not settings_:
        return
    presets = models() if presets is None else presets
    if model:
        presets = {model: _entry(model, presets)}
    given = {k: str(v) for k, v in settings_.items()}
    allowed = [{k: str(v) for k, v in (p.get("knobs") or {}).items()} for p in presets.values()]
    if given not in allowed:
        raise Refusal(
            f"{store}: these settings are not "
            + (
                f"the preset {model!r}"
                if model
                else f"one of the presets {sorted(presets) or 'the admin declared (there are none)'}"
            )
            + "; a store other than the admin's runs a preset whole, or the defaults."
        )


def _inside(store: str, path: str | None) -> str | None:
    if path is None or _admin(store):
        return path
    real = os.path.realpath(path)
    root = os.path.realpath(store)
    if real != root and (not real.startswith(root + os.sep)):
        raise Refusal(f"{os.path.basename(path.rstrip('/')) or path} lies outside your store")
    return path


def _job(store: str, settings_: Mapping, model: str = "", base: job.Job | None = None) -> job.Job:
    presets = models() if model or (settings_ and not _admin(store)) else {}
    settings_ = dict(settings_)
    if model and not settings_:
        settings_ = dict(_entry(model, presets)["knobs"])
    check(store, settings_, presets, model)
    base = base if base is not None else job.current()
    secrets = dict(base.secrets) if _admin(store) else {}
    if model:
        e = _entry(model, presets)
        endpoint, key = _endpoint(e, model, base)
        settings_["VLM_ENDPOINT" if e["kind"] == "reader" else "LAYOUT_ENDPOINT"] = endpoint
        if key:
            secrets["VLM_API_KEY" if e["kind"] == "reader" else "LAYOUT_API_KEY"] = key
    return dataclasses.replace(base, settings=settings_, secrets=secrets)


def books(store: str) -> list[str]:
    return book.Book.list(store)


def book_dir(store: str, name: str) -> str:
    if name not in books(store):
        raise Refusal(f"no book {name!r} in this store; there are {books(store) or 'none'}")
    return os.path.join(store, name)


_SAFE = re.compile("[^\\w.,()-]+", re.UNICODE)


def upload(store: str, scan: str, name: str = "", filename: str = "") -> str:
    from backend import raster

    if not os.path.isfile(scan):
        raise Refusal(f"no file {scan}")
    fname = os.path.basename(filename or scan)
    if (
        fname != (filename or os.path.basename(scan))
        or fname.startswith(".")
        or (not fname.lower().endswith(".pdf"))
    ):
        raise Refusal(f"{filename or fname!r} is not a plain PDF file name")
    if fname in book.ALLOWED or fname.split(".")[0] in ("detect", "read", "truth"):
        raise Refusal(f"{fname!r} is a name the book directory keeps for itself")
    try:
        with raster.open_pdf(scan) as d:
            n = d.page_count
    except Exception as e:
        raise Refusal(f"{fname}: does not open as a PDF ({type(e).__name__}: {e})") from None
    if not n:
        raise Refusal(f"{fname}: a PDF of zero pages")
    stem = name or os.path.splitext(fname)[0]
    safe = _SAFE.sub("-", stem).strip("-")[:80]
    if not safe or set(safe) <= {"."}:
        raise Refusal(f"{stem!r} leaves no name for a book directory")
    dest = os.path.join(store, "processed", safe)
    if os.path.exists(dest):
        raise Refusal(f"the store already holds a book named {safe!r}")
    sha = stamp.sha256(scan)
    for rel in books(store):
        with open(os.path.join(store, rel, "manifest.json"), encoding="utf-8") as f:
            had = (json.load(f).get("source") or {}).get("sha256")
        if had == sha:
            raise Refusal(f"this scan is already the book {rel}: same sha256")
    from backend.page import write_json

    os.makedirs(dest)
    shutil.copy2(scan, os.path.join(dest, fname))
    write_json(
        os.path.join(dest, "manifest.json"),
        {"book": safe, "source": {"name": fname, "sha256": sha}},
        indent=1,
    )
    log(f"book {safe}: {fname}, sha256 {sha[:12]}", book=safe)
    return dest


def _level(snap: dict, kind: str) -> str:
    if snap.get("derived_from"):
        return "corrected"
    return "hybrid" if snap.get("layout") == "own" else kind


def runs(store: str, name: str) -> list[dict]:
    from backend.page import load_pages

    d = book_dir(store, name)
    out = []
    for kind in book.KINDS:
        base = os.path.join(d, kind)
        if not os.path.isdir(base):
            continue
        for label in sorted(os.listdir(base)):
            rd = os.path.join(base, label)
            pages = os.path.join(rd, "pages")
            if not os.path.isdir(pages) or label.endswith(book.ASIDE):
                continue
            snap_path = os.path.join(rd, "run.json")
            snap = {}
            if os.path.isfile(snap_path):
                with open(snap_path, encoding="utf-8") as f:
                    snap = json.load(f)
            try:
                n = len(load_pages(pages))
            except Exception:
                n = 0
            out.append(
                {
                    "kind": kind,
                    "label": label,
                    "identity": snap.get("identity"),
                    "pages": n,
                    "complete": bool(snap),
                    "level": _level(snap, kind),
                    "when": snap.get("when"),
                }
            )
    return out


def _level_one(
    store: str,
    target: str,
    settings: Mapping,
    pages: str | None,
    out: str | None,
    model: str,
    hybrid: bool,
    base: job.Job | None,
) -> str:
    from backend import layout as level_one

    _inside(store, target)
    _inside(store, out)
    kind, suffix = ("read", ".hybrid") if hybrid else ("detect", ".detect")
    with _job(store, settings, model, base).active():
        det = level_one._adapter()
        if os.path.isfile(os.path.join(target, "manifest.json")):
            bk = book.Book.open(target, kind)
            pdf = bk.pdf
            if pdf is None:
                raise Refusal(
                    f"{bk.name}: the manifest names {(bk.manifest.get('source') or {}).get('name')!r} and it is not beside the manifest. The book directory is where the scan lives; a run cannot be measured against a file that is not there."
                )
            out = out or bk.run_dir(kind, det.label())
            target = pdf
        out = out or os.path.splitext(target)[0] + suffix
        return level_one.run(target, out, pages, det=det, hybrid=hybrid)


def detect(
    store: str,
    target: str,
    settings: Mapping,
    pages: str | None = None,
    out: str | None = None,
    model: str = "",
    base: job.Job | None = None,
) -> str:
    return _level_one(store, target, settings, pages, out, model, False, base)


def hybrid(
    store: str,
    target: str,
    settings: Mapping,
    pages: str | None = None,
    out: str | None = None,
    model: str = "",
    base: job.Job | None = None,
) -> str:
    return _level_one(store, target, settings, pages, out, model, True, base)


def _book_of(run_dir: str) -> book.Book | None:
    up = os.path.dirname(os.path.dirname(os.path.abspath(run_dir.rstrip("/"))))
    if os.path.isfile(os.path.join(up, "manifest.json")):
        return book.Book.open(up)
    return None


def read(
    store: str,
    detect_dir: str,
    settings: Mapping,
    out: str | None = None,
    pages: str = "",
    policy: str = "",
    model: str = "",
    base: job.Job | None = None,
) -> str:
    from backend import raster
    from backend.layout import parse_pages
    from backend import driver
    from backend import transport as openai_http

    _inside(store, detect_dir)
    _inside(store, out)
    with _job(store, settings, model, base).active():
        want = None
        if pages:
            with raster.open_pdf(book.pdf_of(detect_dir)) as d:
                want = set(parse_pages(pages, d.page_count))
        pol = driver.policy_for(detect_dir, policy, what="the paid run")
        reader = driver.build_reader(pol)
        if out is None:
            bk = _book_of(detect_dir)
            out = (
                bk.run_dir("read", reader.label())
                if bk is not None
                else os.path.abspath(detect_dir).rstrip("/") + ".read"
            )
        os.makedirs(out, exist_ok=True)
        transport = openai_http.build()
        who = transport.check()
        log(
            f"endpoint {who['endpoint']}: answers {who['models_on_server']}, we ask {who['asking_for']} — matched"
        )
        t = driver.read_book(
            detect_dir, out, reader, transport, resume=knobs.knob("RESUME") == "1", pages_want=want
        )
        driver.report(t)
        p = driver.snapshot(
            detect_dir,
            out,
            reader,
            transport,
            t,
            {"detect": detect_dir, "out": out, "pages": pages, "policy": pol.name},
        )
        log(f"snapshot: {p}")
        return out


def _run_of(store: str, name: str, kind: str, label: str) -> tuple[book.Book, str]:
    b = book.Book.open(book_dir(store, name))
    have = b.runs(kind)
    if label not in have:
        raise Refusal(
            f"{name}: no {kind} run labelled {label!r}; there {('are ' + ', '.join(have) if have else 'is none')}"
        )
    return (b, b.run_dir(kind, label))


def _page_json(pages_dir: str, index: int, whose: str) -> dict:
    path = os.path.join(pages_dir, f"{index:04d}.json")
    if not os.path.isfile(path):
        raise Refusal(f"no page {index} in {whose}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def page(store: str, name: str, kind: str, label: str, index: int) -> dict:

    _, rd = _run_of(store, name, kind, label)
    return dataclasses.asdict(document.gather_page(rd, index))


DPI_LEAST, DPI_MOST = (24.0, 300.0)


@functools.lru_cache(maxsize=48)
def _render(pdf: str, sha: str, index: int, dpi: float) -> bytes:
    from backend import raster

    with raster.open_pdf(pdf) as doc:
        if not 0 <= index < doc.page_count:
            raise Refusal(f"no page {index}: the scan has {doc.page_count}")
        return raster.render_png(doc[index], dpi)


def page_image(store: str, name: str, index: int, dpi: float = 110.0) -> bytes:
    b = book.Book.open(book_dir(store, name))
    if b.pdf is None:
        raise Refusal(f"{name}: the scan is not beside the manifest")
    if not DPI_LEAST <= dpi <= DPI_MOST:
        raise Refusal(f"dpi {dpi:g} is outside {DPI_LEAST:g}..{DPI_MOST:g}")
    return _render(os.path.realpath(b.pdf), b.sha256 or "", int(index), float(dpi))


def crop_png(store: str, name: str, kind: str, label: str, anchor: str, dpi: float | None = None) -> bytes:
    from backend import raster
    from backend.page import parse_anchor

    b, rd = _run_of(store, name, kind, label)
    try:
        index, block_id = parse_anchor(anchor)
    except ValueError as e:
        raise Refusal(str(e)) from None
    if block_id is None:
        raise Refusal(f"a crop is one block, p<index>-b<block_id>, not {anchor!r}")
    kept = os.path.join(rd, "crops", f"{anchor}.png")
    if os.path.isfile(kept):
        with open(kept, "rb") as f:
            return f.read()
    pg = _page_json(os.path.join(rd, "pages"), index, f"{kind}/{label}")
    blk = next((x for x in pg["blocks"] if x["block_id"] == block_id), None)
    if blk is None:
        raise Refusal(f"no block {anchor} in {kind}/{label}")
    if b.pdf is None:
        raise Refusal(f"{name}: the scan is not beside the manifest")
    if dpi is not None and (not DPI_LEAST <= dpi <= DPI_MOST):
        raise Refusal(f"dpi {dpi:g} is outside {DPI_LEAST:g}..{DPI_MOST:g}")
    if dpi is None:
        said = stamp.knob_values(book.snapshot_beside(os.path.join(rd, "pages")) or {})
        dpi = float(said["CROP_DPI"]) if said.get("CROP_DPI") else None
    with raster.open_pdf(b.pdf) as doc:
        png, _facts = raster.cut_png(doc, index, blk["box"], float(pg["dpi"]), dpi=dpi)
    return png


def run(store: str, name: str, kind: str, label: str) -> dict:
    b, rd = _run_of(store, name, kind, label)
    pages = os.path.join(rd, "pages")
    snap = book.snapshot_beside(pages) or {}
    return {
        "kind": kind,
        "label": label,
        "level": _level(snap, kind),
        "identity": snap.get("identity"),
        "when": snap.get("when"),
        "dpi": (snap.get("raster") or {}).get("dpi"),
        "policy": book.policy_beside(pages).snapshot(),
        "pages": sorted(int(n[:4]) for n in os.listdir(pages) if n.endswith(".json") and n[:4].isdigit()),
        "truth": _truth_of(b),
        "observed": document.answers_present(rd),
        "derived_from": snap.get("derived_from"),
        "corrections": snap.get("corrections") or [],
        "stale": corr.stale(rd) if snap.get("derived_from") else False,
    }


def _truth(b: book.Book) -> tuple[str | None, str | None]:
    t = truth.of(b)
    return (t, None if t is None or t == b.truth_dir else truth.relative(t))


def _truth_of(b: book.Book) -> str | None:
    t = truth.of(b)
    return None if t is None else ("own" if t == b.truth_dir else "borrowed")


def pairs(
    cfg: settings.Settings,
    store: str,
    name: str,
    kind: str,
    label: str,
    index: int,
    truth_side: bool = False,
) -> dict:
    from backend.page import anchor

    b, _ = _run_of(store, name, kind, label)
    t, arg = _truth(b)
    if t is None:
        raise Refusal(f"{name} has no truth and no bench shares its scan: nothing to pair {kind}/{label} against")
    res = measure.pairs(cfg.metrics_url, cfg.relative(store), name, kind, label, index, arg)
    if truth_side:
        t = truth.page(t, index)
        res["truth"] = [
            {
                "anchor": anchor(index, x["block_id"]),
                "block_id": x["block_id"],
                "label": x["label"],
                "box": x["box"],
                "order": x.get("order"),
            }
            for x in t["blocks"]
        ]
        res["out_of_scope"] = (t.get("meta") or {}).get("out_of_scope") or []
    else:
        keep = ("run", "verdict", "label_ok", "fate")
        res["pairs"] = [{k: e.get(k) for k in keep} for e in res["pairs"]]
        res["extras"] = [{"run": e["run"], "verdict": e["verdict"]} for e in res["extras"]]
    return res


def _pages_of(pdf: str | None, spec: str) -> list | None:
    from backend.layout import parse_pages

    if not spec:
        return None
    if not pdf:
        raise Refusal("no scan to count pages against")
    with raster.open_pdf(pdf) as doc:
        return parse_pages(spec, doc.page_count)


def bench(
    db,
    cfg: settings.Settings,
    store: str,
    path: str,
    run: str = "",
    kind: str = "detect",
    only: list | None = None,
    pages: str = "",
    base: job.Job | None = None,
) -> str:
    _inside(store, path)
    name = os.path.relpath(path, store)
    b = book.Book.open(path)
    label = run or os.path.basename(b.one_run(kind))
    want = _pages_of(b.pdf, pages)
    _, arg = _truth(b)
    with _job(store, {}, "", base).active():
        recs = measure.measure(cfg.metrics_url, cfg.relative(store), name, arg, kind, label, want, only)
        log(f"{name} {kind}/{label}: {len(recs)} records", n=len(recs), of=len(recs))
    db.add_measurements(store, name, kind, label, recs, want, stamp.commit())
    return f"{name} {kind}/{label}: {len(recs)} records"


def measure_page(
    cfg: settings.Settings, store: str, name: str, kind: str, label: str, index: int, truth_side: bool = False
) -> list[dict]:
    b, _ = _run_of(store, name, kind, label)
    _, arg = _truth(b)
    recs = measure.measure(cfg.metrics_url, cfg.relative(store), name, arg, kind, label, [int(index)])
    return recs if truth_side else [_run_side(r) for r in recs]


def _run_side(rec: dict) -> dict:
    scalars = {
        k: ({kk: v for kk, v in s.items() if kk != "per"} if s.get("side") == "truth" else s)
        for k, s in rec["scalars"].items()
    }
    return {**rec, "scalars": scalars, "detail": {}}


def series(db, store: str, name: str, kind: str, label: str) -> list[dict]:
    from backend.db import as_dict
    from backend.identity import staleness

    b, rd = _run_of(store, name, kind, label)
    snap = book.snapshot_beside(os.path.join(rd, "pages"))
    t, _ = _truth(b)
    now = truth.fingerprint(t) if t else None
    out = []
    for row in db.measurements(store, name, kind, label):
        d = as_dict(row) or {}
        d["state"] = staleness(d.get("identity"), snap, d.get("source_sha256"), d.get("truth_sha256"), now)
        out.append(d)
    return out


def results(db, store: str, name: str, kind: str, label: str) -> dict:
    rows = series(db, store, name, kind, label)
    if not rows:
        raise Refusal(f"{name} {kind}/{label} was not measured yet")
    last = rows[-1]["when"]
    return {"when": last, "records": [r for r in rows if r["when"] == last]}


def document_of(store: str, name: str, kind: str, label: str) -> dict:
    _, rd = _run_of(store, name, kind, label)
    return document.write(rd)


def truth_page(store: str, name: str, index: int) -> dict:
    b = book.Book.open(book_dir(store, name))
    t = truth.of(b)
    if t is None:
        raise Refusal(f"{name} has no truth")
    return truth.page(t, index)


def label_page(store: str, name: str, index: int, page: dict, author: str) -> dict:
    b = book.Book.open(book_dir(store, name))
    if not b.truth_dir:
        raise Refusal(f"{name} has no truth of its own; start one first")
    if page["index"] != index:
        raise Refusal(f"the page says index {page['index']}, the route says {index}")
    base = truth.page(b.truth_dir, index)
    same = ("width", "height", "dpi")
    if any(page[k] != base[k] for k in same):
        raise Refusal(f"a layer keeps the page's {', '.join(same)}: {[base[k] for k in same]}")
    return {"layer": truth.relative(truth.write_layer(b.truth_dir, page, author)), "page": truth.page(b.truth_dir, index)}


def start_truth(store: str, name: str, kind: str, label: str) -> dict:
    b, rd = _run_of(store, name, kind, label)
    if not b.pdf:
        raise Refusal(f"{name} has no scan")
    dpi = ((book.snapshot_beside(os.path.join(rd, "pages")) or {}).get("raster") or {}).get("dpi")
    if not dpi:
        raise Refusal(f"{kind}/{label} does not record the dpi it was drawn at")
    t = truth.blank(b.root, b.pdf, float(dpi))
    return {"truth": truth.relative(t), "pages": len(truth.pages(t)), "dpi": float(dpi)}


def class_table() -> dict:
    return classes.TABLE


def export(store: str, name: str, kind: str, label: str, fmt: str, math: str = "cdn") -> tuple[Iterator[bytes], str, str]:
    import tempfile
    from urllib.parse import quote

    b, rd = _run_of(store, name, kind, label)
    if b.pdf is None:
        raise Refusal(f"{name}: the scan is not beside the manifest")
    doc = document.write(rd)
    kept = os.path.join(rd, "crops")
    said = stamp.knob_values(book.snapshot_beside(os.path.join(rd, "pages")) or {})
    dpi = float(said["CROP_DPI"]) if said.get("CROP_DPI") else None
    page_dpi = {p["index"]: float(p["dpi"]) for p in doc["pages"]}
    spool = tempfile.SpooledTemporaryFile(max_size=32 << 20)
    with raster.open_pdf(b.pdf) as scan:

        def crop(blk: dict) -> bytes:
            path = os.path.join(kept, f"{blk['anchor']}.png")
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
            return raster.cut_png(scan, blk["page"], blk["box"], page_dpi[blk["page"]], dpi=dpi)[0]

        for chunk in export_mod.render(fmt, doc, crop, math):
            spool.write(chunk.encode("utf-8"))
    spool.seek(0)
    media, ext = export_mod.FORMATS[fmt]
    stem = os.path.splitext(doc["source"]["name"])[0] or "book"
    plain = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "book"
    disposition = f'attachment; filename="{plain}.{label}.{ext}"; filename*=UTF-8\'\'{quote(f"{stem}.{label}.{ext}")}'
    return (iter(lambda: spool.read(1 << 20), b""), media, disposition)


def corrections(store: str, name: str, kind: str, label: str) -> dict:
    _, rd = _run_of(store, name, kind, label)
    base = corr.base_of(rd)
    if not os.path.isdir(base):
        raise Refusal(f"{kind}/{label} derives from a run that is gone")
    derived = corr.derived_of(base)
    have = os.path.isdir(derived)
    return {
        "base": os.path.basename(base),
        "run": os.path.basename(derived) if have else None,
        "corrections": corr.listed(base),
        "stale": corr.stale(derived) if have else False,
    }


def correct(store: str, name: str, kind: str, label: str, c: dict, author: str) -> dict:
    _, rd = _run_of(store, name, kind, label)
    corr.add(corr.base_of(rd), c, author)
    return corrections(store, name, kind, label)


def rederive(store: str, name: str, kind: str, label: str) -> dict:
    _, rd = _run_of(store, name, kind, label)
    corr.again(corr.base_of(rd))
    return corrections(store, name, kind, label)


def uncorrect(store: str, name: str, kind: str, label: str, n: int) -> dict:
    _, rd = _run_of(store, name, kind, label)
    base = corr.base_of(rd)
    corr.remove(base, n)
    return corrections(store, name, kind, os.path.basename(base))
