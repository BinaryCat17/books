import dataclasses
import functools
import json
import os
import re
import shutil
from collections.abc import Mapping
from backend import raster
from backend import store as book
from backend import job
from backend import knobs
from backend import protocol as served
from backend import identity as stamp
from backend.errors import Refusal
from backend.log import log
from backend import document, measure, settings


def admin() -> str:
    return settings.home()


def registry(raw: object, where: str = "models.json") -> dict:
    if not isinstance(raw, dict):
        raise Refusal(f"{where}: not a mapping of names to entries")
    out = {}
    for name, e in raw.items():
        if not isinstance(e, dict):
            raise Refusal(f"{where}: {name}: an entry is a mapping")
        kind = e.get("kind")
        if kind not in served.KINDS:
            raise Refusal(f"{where}: {name}: kind {kind!r} is not one of {served.KINDS}")
        kn = e.get("knobs", {})
        if not isinstance(kn, dict):
            raise Refusal(f"{where}: {name}: knobs must be a mapping")
        unknown = sorted(set(kn) - set(knobs.names()))
        if unknown:
            raise Refusal(f"{where}: {name}: knobs nothing declares: {unknown}")
        has_endpoint, has_image = (bool(e.get("endpoint")), bool(e.get("image")))
        if has_endpoint == has_image:
            raise Refusal(
                f"{where}: {name}: exactly one of `endpoint` and `image`: either the model answers somewhere, or an image and a provider will bring one up."
            )
        if has_image and (not e.get("provider")):
            raise Refusal(f"{where}: {name}: an image needs a `provider`")
        out[name] = {**e, "knobs": {k: str(v) for k, v in kn.items()}}
    return out


def models_path() -> str:
    return os.path.join(admin(), "models.json")


def models() -> dict:
    path = models_path()
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return registry(json.load(f), path)


def write_models(raw: object) -> dict:
    checked = registry(raw)
    from backend.page import write_json

    write_json(models_path(), raw, indent=1)
    return checked


def _admin(store: str) -> bool:
    return os.path.realpath(store) == os.path.realpath(admin())


def _entry(model: str, presets: Mapping) -> dict:
    if model not in presets:
        raise Refusal(f"no model {model!r} in the registry; there are {sorted(presets) or 'none'}")
    return dict(presets[model])


def check(store: str, settings: Mapping, presets: Mapping | None = None, model: str = "") -> None:
    if _admin(store) or not settings:
        return
    presets = models() if presets is None else presets
    if model:
        presets = {model: _entry(model, presets)}
    given = {k: str(v) for k, v in settings.items()}
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


def _with_endpoint(settings: Mapping, e: dict, model: str) -> dict:
    if not e.get("endpoint"):
        raise Refusal(f"model {model!r} names an image and no endpoint, and nothing here brings one up yet.")
    out = dict(settings)
    if e["kind"] == "reader":
        out["VLM_ENDPOINT"] = str(e["endpoint"])
    else:
        out["LAYOUT_ENDPOINT"] = str(e["endpoint"])
    return out


def _job(store: str, settings: Mapping, model: str = "", base: job.Job | None = None) -> job.Job:
    presets = models()
    settings = dict(settings)
    if model and (not settings):
        settings = dict(_entry(model, presets)["knobs"])
    check(store, settings, presets, model)
    base = base if base is not None else job.current()
    secrets = dict(base.secrets) if _admin(store) else {}
    if model:
        e = _entry(model, presets)
        settings = _with_endpoint(settings, e, model)
        if e.get("api_key"):
            name = "VLM_API_KEY" if e["kind"] == "reader" else "LAYOUT_API_KEY"
            secrets[name] = str(e["api_key"])
    return dataclasses.replace(base, settings=settings, secrets=secrets)


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
            if not os.path.isdir(pages):
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
                    "level": "hybrid" if snap.get("layout") == "own" else kind,
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


def html(
    store: str, run_dir: str, settings: Mapping, out: str | None = None, base: job.Job | None = None
) -> str:
    from backend import export_html as html_mod

    _inside(store, run_dir)
    _inside(store, out)
    with _job(store, settings, "", base).active():
        d = book.run_dir(run_dir, "an export")
        named = out is not None
        out = out or book.home_for(d, store)
        if (
            not named
            and os.path.isdir(out)
            and os.listdir(out)
            and (not html_mod.is_our_dir(out))
            and (not os.path.isfile(os.path.join(out, "manifest.json")))
        ):
            raise Refusal(
                f"{out} already holds something not ours: no manifest.json and no `{html_mod.ASSETS}/run.json`, so it is neither a book nor a build of an export. Overwriting it silently is not allowed: give --out or remove it by hand."
            )
        html_mod.build(d, out)
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
        "level": "hybrid" if snap.get("layout") == "own" else kind,
        "identity": snap.get("identity"),
        "when": snap.get("when"),
        "dpi": (snap.get("raster") or {}).get("dpi"),
        "policy": book.policy_beside(pages).snapshot(),
        "pages": sorted(int(n[:4]) for n in os.listdir(pages) if n.endswith(".json") and n[:4].isdigit()),
        "truth": b.truth_dir is not None,
        "observed": document.answers_present(rd),
    }


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
    if not b.truth_dir:
        raise Refusal(f"{name} has no truth: nothing to pair {kind}/{label} against")
    res = measure.pairs(cfg.metrics_url, cfg.relative(store), name, kind, label, index)
    if truth_side:
        t = _page_json(book.pages_dir(b.truth_dir, "truth"), index, "truth")
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
    with _job(store, {}, "", base).active():
        recs = measure.measure(cfg.metrics_url, cfg.relative(store), name, kind, label, want, only)
        log(f"{name} {kind}/{label}: {len(recs)} records", n=len(recs), of=len(recs))
    db.add_measurements(store, name, kind, label, recs, want, stamp.commit())
    return f"{name} {kind}/{label}: {len(recs)} records"


def measure_page(
    cfg: settings.Settings, store: str, name: str, kind: str, label: str, index: int
) -> list[dict]:
    _run_of(store, name, kind, label)
    return measure.measure(cfg.metrics_url, cfg.relative(store), name, kind, label, [int(index)])


def series(db, store: str, name: str, kind: str, label: str) -> list[dict]:
    from backend.db import as_dict
    from backend.identity import staleness

    _, rd = _run_of(store, name, kind, label)
    snap = book.snapshot_beside(os.path.join(rd, "pages"))
    out = []
    for row in db.measurements(store, name, kind, label):
        d = as_dict(row) or {}
        d["state"] = staleness(d.get("identity"), snap, d.get("source_sha256"))
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
