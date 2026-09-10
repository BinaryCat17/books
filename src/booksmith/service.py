"""The service: what the CLI and the web share, one function per command.

A store is a root directory in the shape `core/book.py` declares, `bench/`
and `processed/` under it. A user owns one, under `users/` in the data home;
the admin's is the data home itself. Ownership of a book, its runs and its
truth is the store it lies in. Every function takes the store and the
settings of the run and works under a job bound to them, on paths inside
that store, outputs included. A store other than the admin's may run only a
preset from the admin's `models.json`, or the registry's defaults.

Models are data: `models.json` is `{name: {kind, endpoint | image + provider,
knobs, api_key, idle_s, budget}}`. `kind` is layout, reader or hybrid; `knobs`
are the values a preset runs with; the endpoint is where the model answers,
or the image and provider are what will bring one up. A job named after an
entry has the entry's endpoint filled into its knobs after the store's
settings were checked, and the entry's key on its secrets, never in a
snapshot. The fingerprint, label and identity stay the model's own.
"""
import dataclasses
import functools
import json
import os
import re
import shutil
from collections.abc import Mapping

from booksmith.core import book, config, job, knobs, served, stamp
from booksmith.core.errors import Refusal
from booksmith.core.log import log


def admin() -> str:
    """The admin's store: the data home."""
    return config.home()


def registry(raw: object, where: str = "models.json") -> dict:
    """The registry checked entry by entry, knob values as strings. A refusal
    names the entry and the field: an entry that names no endpoint and no
    image, or both, or a knob nothing declares, is not a model."""
    if not isinstance(raw, dict):
        raise Refusal(f"{where}: not a mapping of names to entries")
    out = {}
    for name, e in raw.items():
        if not isinstance(e, dict):
            raise Refusal(f"{where}: {name}: an entry is a mapping")
        kind = e.get("kind")
        if kind not in served.KINDS:
            raise Refusal(f"{where}: {name}: kind {kind!r} is not one of "
                          f"{served.KINDS}")
        kn = e.get("knobs", {})
        if not isinstance(kn, dict):
            raise Refusal(f"{where}: {name}: knobs must be a mapping")
        unknown = sorted(set(kn) - set(knobs.names()))
        if unknown:
            raise Refusal(f"{where}: {name}: knobs nothing declares: {unknown}")
        has_endpoint, has_image = bool(e.get("endpoint")), bool(e.get("image"))
        if has_endpoint == has_image:
            raise Refusal(
                f"{where}: {name}: exactly one of `endpoint` and `image`: "
                f"either the model answers somewhere, or an image and a "
                f"provider will bring one up.")
        if has_image and not e.get("provider"):
            raise Refusal(f"{where}: {name}: an image needs a `provider`")
        out[name] = {**e, "knobs": {k: str(v) for k, v in kn.items()}}
    return out


def models_path() -> str:
    return os.path.join(admin(), "models.json")


def models() -> dict:
    """The presets the admin declared, checked."""
    path = models_path()
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return registry(json.load(f), path)


def write_models(raw: object) -> dict:
    """The registry written whole, checked first: a file that does not pass
    `registry` is never on disk."""
    checked = registry(raw)
    from booksmith.core.page import write_json
    write_json(models_path(), raw, indent=1)
    return checked


def _admin(store: str) -> bool:
    return os.path.realpath(store) == os.path.realpath(admin())


def _entry(model: str, presets: Mapping) -> dict:
    if model not in presets:
        raise Refusal(f"no model {model!r} in the registry; there are "
                      f"{sorted(presets) or 'none'}")
    return dict(presets[model])


def check(store: str, settings: Mapping, presets: Mapping | None = None,
          model: str = "") -> None:
    """A store other than the admin's runs a preset whole, or nothing at all.
    With `model` named, the one entry; else any. Asked before the endpoint
    is filled in, or a user's preset would never equal their settings."""
    if _admin(store) or not settings:
        return
    presets = models() if presets is None else presets
    if model:
        presets = {model: _entry(model, presets)}
    given = {k: str(v) for k, v in settings.items()}
    allowed = [{k: str(v) for k, v in (p.get("knobs") or {}).items()}
               for p in presets.values()]
    if given not in allowed:
        raise Refusal(
            f"{store}: these settings are not "
            + (f"the preset {model!r}" if model else "one of the presets "
               f"{sorted(presets) or 'the admin declared (there are none)'}")
            + "; a store other than the admin's runs a preset whole, or the "
              "defaults.")


def _inside(store: str, path: str | None) -> str | None:
    """A path a store other than the admin's may read or write: one under
    the store by its real path, so a link inside the store reaches nothing
    outside it. None passes: it is a default the callee derives inside."""
    if path is None or _admin(store):
        return path
    real = os.path.realpath(path)
    root = os.path.realpath(store)
    if real != root and not real.startswith(root + os.sep):
        # Named without the root: the server's paths are the server's.
        raise Refusal(f"{os.path.basename(path.rstrip('/')) or path} lies "
                      f"outside your store")
    return path


def _with_endpoint(settings: Mapping, e: dict, model: str) -> dict:
    """The entry's address as the knob the run reads; the adapter that reads
    it is `served` for a layout or hybrid model, the transport for a reader."""
    if not e.get("endpoint"):
        raise Refusal(
            f"model {model!r} names an image and no endpoint, and nothing "
            f"here brings one up yet.")
    out = dict(settings)
    if e["kind"] == "reader":
        out["VLM_ENDPOINT"] = str(e["endpoint"])
    else:
        out["LAYOUT_ADAPTER"] = "served"
        out["LAYOUT_ENDPOINT"] = str(e["endpoint"])
    return out


def _job(store: str, settings: Mapping, model: str = "",
         base: job.Job | None = None) -> job.Job:
    """The job of one run: the caller's job, or the current one, with the
    settings checked, the entry's endpoint filled in after the check, and the
    entry's key among the secrets. Empty settings under a named entry are
    the entry's knobs: a preset runs whole, never under the defaults by
    accident. A store other than the admin's starts with no secrets but the
    entry's: the process's own key is the operator's, not the tenant's. The
    caller's job keeps its stop and its sink, so two jobs stop apart."""
    presets = models()
    settings = dict(settings)
    if model and not settings:
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


def open_book(path: str, kind: str, label: str) -> tuple:
    """The book at `path` and one of its runs, as `bench` opens them: a bench
    is a book with `truth/`, a processed book the other half. Asked here rather
    than by catching `Unmeasurable` from `open`: a caught refusal cannot tell
    "no truth here, which is fine" from "this path is wrong"."""
    from booksmith.datasets.bench import Bench
    root = path.rstrip("/")
    if not os.path.isdir(root):
        # Said before either door is tried: both openers answer a missing path
        # by describing what they wanted to find in it, which sends the reader
        # looking for a file in a directory that does not exist.
        raise Refusal(f"{path} is not a directory. This takes a book: "
                      f"bench/<name> or processed/<name>.")
    has_truth = (os.path.isdir(os.path.join(root, "truth"))
                 or os.path.basename(root) == "truth")
    b = Bench.open(root) if has_truth else Bench.no_truth(root)
    return b, b.run(label, kind)


# ------------------------------------------------------------------ books
def books(store: str) -> list[str]:
    return book.Book.list(store)


def book_dir(store: str, name: str) -> str:
    """The directory of a book named as `books` lists it, `bench/<x>` or
    `processed/<x>`, inside the store; anything else is refused by name."""
    if name not in books(store):
        raise Refusal(f"no book {name!r} in this store; there are "
                      f"{books(store) or 'none'}")
    return os.path.join(store, name)


_SAFE = re.compile(r"[^\w.,()-]+", re.UNICODE)


def upload(store: str, scan: str, name: str = "", filename: str = "") -> str:
    """A scan into the store as a book: `processed/<name>/` with the scan
    beside its manifest under `filename`, the hash taken once here and
    trusted after. Everything is checked before anything is placed: the file
    must open as a PDF, the file name must be a plain one that is not one of
    the book directory's own, and a name already taken, or a scan the store
    already holds under another name, is refused, since two books of one
    scan measure as one and read as two."""
    from booksmith.core import raster
    if not os.path.isfile(scan):
        raise Refusal(f"no file {scan}")
    fname = os.path.basename(filename or scan)
    if (fname != (filename or os.path.basename(scan)) or fname.startswith(".")
            or not fname.lower().endswith(".pdf")):
        raise Refusal(f"{filename or fname!r} is not a plain PDF file name")
    if fname in book.ALLOWED or fname.split(".")[0] in ("detect", "read", "look", "truth"):
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
    from booksmith.core.page import write_json
    os.makedirs(dest)
    shutil.copy2(scan, os.path.join(dest, fname))
    write_json(os.path.join(dest, "manifest.json"),
               {"book": safe, "source": {"name": fname, "sha256": sha}}, indent=1)
    log(f"book {safe}: {fname}, sha256 {sha[:12]}", book=safe)
    return dest


def runs(store: str, name: str) -> list[dict]:
    """Every run of a book: kind, label, identity, page count, and whether
    its snapshot is there, which is what makes a directory a run."""
    from booksmith.core.page import load_pages
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
            out.append({"kind": kind, "label": label, "identity": snap.get("identity"),
                        "pages": n, "complete": bool(snap),
                        "level": "hybrid" if snap.get("layout") == "own" else kind,
                        "when": snap.get("when")})
    return out


# ------------------------------------------------------------- level one
def _level_one(store: str, target: str, settings: Mapping, pages: str | None,
               out: str | None, model: str, hybrid: bool,
               base: job.Job | None) -> str:
    from booksmith.processing.layout import detect as level_one
    _inside(store, target)
    _inside(store, out)
    kind, suffix = ("read", ".hybrid") if hybrid else ("detect", ".detect")
    with _job(store, settings, model, base).active():
        # The adapter before the pages: its label files the run, and a run
        # that cannot be filed refuses before a page is rendered. Built once
        # and handed to the loop, so one run loads one session.
        det = level_one._adapter()
        if os.path.isfile(os.path.join(target, "manifest.json")):
            bk = book.Book.open(target, kind)
            pdf = bk.pdf
            if pdf is None:
                raise Refusal(
                    f"{bk.name}: the manifest names "
                    f"{(bk.manifest.get('source') or {}).get('name')!r} and it is "
                    f"not beside the manifest. The book directory is where the "
                    f"scan lives; a run cannot be measured against a file that "
                    f"is not there.")
            out = out or bk.run_dir(kind, det.label())
            target = pdf
        out = out or os.path.splitext(target)[0] + suffix
        return level_one.run(target, out, pages, det=det, hybrid=hybrid)


def detect(store: str, target: str, settings: Mapping, pages: str | None = None,
           out: str | None = None, model: str = "",
           base: job.Job | None = None) -> str:
    """Level one over a book directory or a bare PDF. Returns the run
    directory: under the book as `detect/<label>/`, else beside the file."""
    return _level_one(store, target, settings, pages, out, model, False, base)


def hybrid(store: str, target: str, settings: Mapping, pages: str | None = None,
           out: str | None = None, model: str = "",
           base: job.Job | None = None) -> str:
    """Boxes and content in one call from a served hybrid model, filed as a
    read run with its own boxes: `read/<label>/` under the book, else beside
    the file. Returns the run directory."""
    return _level_one(store, target, settings, pages, out, model, True, base)


# ------------------------------------------------------------- level two
def _book_of(run_dir: str) -> book.Book | None:
    """The book a run directory lies under, or None beside a bare file."""
    up = os.path.dirname(os.path.dirname(os.path.abspath(run_dir.rstrip("/"))))
    if os.path.isfile(os.path.join(up, "manifest.json")):
        return book.Book.open(up)
    return None


def read(store: str, detect_dir: str, settings: Mapping, out: str | None = None,
         pages: str = "", policy: str = "", model: str = "",
         base: job.Job | None = None) -> str:
    """Level two over a detect run, through `VLM_ENDPOINT`; `pages` as
    `books detect` counts them, from one. Returns the run directory:
    `read/<label>/` under the book the detect run lies in, else
    `<detect dir>.read`, unless named."""
    from booksmith.core import raster
    from booksmith.processing.layout.detect import parse_pages
    from booksmith.processing.read import driver
    from booksmith.processing.read.transports import openai_http
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
            out = (bk.run_dir("read", reader.label()) if bk is not None
                   else os.path.abspath(detect_dir).rstrip("/") + ".read")
        os.makedirs(out, exist_ok=True)
        transport = openai_http.build()
        who = transport.check()
        log(f"endpoint {who['endpoint']}: answers {who['models_on_server']}, "
            f"we ask {who['asking_for']} — matched")
        t = driver.read_book(detect_dir, out, reader, transport,
                             resume=knobs.knob("RESUME") == "1", pages_want=want)
        driver.report(t)
        p = driver.snapshot(detect_dir, out, reader, transport, t,
                            {"detect": detect_dir, "out": out, "pages": pages,
                             "policy": pol.name})
        log(f"snapshot: {p}")
        return out


def crop(store: str, detect_dir: str, settings: Mapping, out: str | None = None,
         pages: str = "", policy: str = "", base: job.Job | None = None) -> dict:
    """What `books read` would send, cut by its own path: the driver in
    preview, nothing sent. Returns the tally."""
    from booksmith.core import raster
    from booksmith.processing.layout.detect import parse_pages
    from booksmith.processing.read import driver
    _inside(store, detect_dir)
    _inside(store, out)
    with _job(store, settings, "", base).active():
        d = book.run_dir(detect_dir, "books crop")
        out = out or (os.path.abspath(d).rstrip("/") + ".crop")
        pol = driver.policy_for(d, policy, what="the preview")
        os.makedirs(out, exist_ok=True)
        reader = driver.build_reader(pol)
        want = None
        if pages:
            with raster.open_pdf(book.pdf_of(d)) as doc:
                want = set(parse_pages(pages, doc.page_count))
        t = driver.read_book(d, out, reader, None, resume=False, pages_want=want,
                             preview=True)
        t["out"] = out
        return t


# ----------------------------------------------------------------- the book
def html(store: str, run_dir: str, settings: Mapping, out: str | None = None,
         base: job.Job | None = None) -> str:
    """The book as HTML out of a detect or read run: into the book directory
    the run lies in, else the store's `processed/` under the scan's name,
    unless named. That second default is guarded: a non-empty directory
    there that is neither a book nor a build of ours is a refusal out loud.
    A named `out` is the caller's to overwrite. Returns the build directory."""
    from booksmith.processing.assemble import html as html_mod
    _inside(store, run_dir)
    _inside(store, out)
    with _job(store, settings, "", base).active():
        d = book.run_dir(run_dir, "books html")
        named = out is not None
        out = out or book.home_for(d, store)
        if (not named and os.path.isdir(out) and os.listdir(out)
                and not html_mod.is_our_dir(out)
                and not os.path.isfile(os.path.join(out, "manifest.json"))):
            raise Refusal(
                f"{out} already holds something not ours: no manifest.json "
                f"and no `{html_mod.ASSETS}/run.json`, so it is neither a book "
                f"nor a build of `books html`. Overwriting it silently is not "
                f"allowed: give --out or remove it by hand.")
        html_mod.build(d, out)
        return out


def overlay(store: str, pdf: str, truth: str | None, detect_dir: str | None,
            out: str | None = None, pages: str = "",
            base: job.Job | None = None) -> str:
    """Boxes over the pages, for the eye: truth, the model's, or both.
    Returns the PDF written."""
    from booksmith.datasets import look
    from booksmith.processing.layout import detect as level_one
    from booksmith.core import raster
    for p in (pdf, truth, detect_dir, out):
        _inside(store, p)
    marks = [(book.pages_dir(truth, "--truth"), "T")] if truth else []
    if detect_dir:
        marks.append((book.pages_dir(detect_dir, "--detect"), "M"))
    if not marks:
        raise Refusal("nothing to draw: give --truth and/or --detect")
    with _job(store, {}, "", base).active():
        out = out or look.look_at(pdf, detect_dir)
        only = None
        if pages:
            with raster.open_pdf(pdf) as doc:
                only = level_one.parse_pages(pages, doc.page_count)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        look.build(pdf, out, marks, only=only)
        return out


# -------------------------------------------------------------- the viewer
# What a page viewer asks for, by name: a run as the viewer opens it, one of
# its pages as data, the scan's page as an image, one block's crop, and the
# metric's pairs on a page where the book has truth. None of it is a job:
# each answer is one page read on demand. Page renders are kept in a small
# cache keyed by the scan's hash, a viewer asking for one page many times.

def _run_of(store: str, name: str, kind: str, label: str) -> tuple[book.Book, str]:
    """A book and one of its runs, both by name inside the store. A run is a
    directory with its snapshot and its pages, as the listing counts them:
    a half-made one is refused here as it is hidden there."""
    b = book.Book.open(book_dir(store, name))
    have = b.runs(kind)
    if label not in have:
        raise Refusal(f"{name}: no {kind} run labelled {label!r}; there "
                      f"{'are ' + ', '.join(have) if have else 'is none'}")
    return b, b.run_dir(kind, label)


def _page_json(pages_dir: str, index: int, whose: str) -> dict:
    path = os.path.join(pages_dir, f"{index:04d}.json")
    if not os.path.isfile(path):
        raise Refusal(f"no page {index} in {whose}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run(store: str, name: str, kind: str, label: str) -> dict:
    """One run as the viewer opens it: identity, the policy its labels are
    read by, the raster dpi its boxes are in, the pages it has, and whether
    the book has truth to pair it against."""
    from booksmith.datasets.bench import Run
    from booksmith.processing.assemble import html as html_mod
    b, rd = _run_of(store, name, kind, label)
    r = Run.open(rd)
    return {"kind": kind, "label": label, "level": r.level,
            "identity": r.snapshot.get("identity"), "when": r.snapshot.get("when"),
            "dpi": (r.snapshot.get("raster") or {}).get("dpi"),
            "policy": r.policy.snapshot(),
            "pages": sorted(int(n[:4]) for n in os.listdir(r.pages_dir)
                            if n.endswith(".json") and n[:4].isdigit()),
            "truth": b.truth_dir is not None,
            "observed": html_mod.answers_present(rd)}


def page(store: str, name: str, kind: str, label: str, index: int) -> dict:
    """One page of a run as the book would show it: every block with its
    role by the run's own policy, what reading said of it, how it nests and
    repeats. The builder's own data pass, one page of it."""
    from booksmith.processing.assemble import html as html_mod
    _, rd = _run_of(store, name, kind, label)
    return dataclasses.asdict(html_mod.gather_page(rd, index))


def pairs(store: str, name: str, kind: str, label: str, index: int,
          truth_side: bool = False) -> dict:
    """The contour metric's pairs on one page of a book that has truth, the
    list `compare_pages` describes. With `truth_side` the truth blocks ride
    along and each entry names its truth anchor and pass A's diagnosis;
    without, an entry keeps the run anchor, the verdict, the label
    agreement and the fate, and an extra its verdict -- the number's own
    words on the run's boxes, and nothing of where or what the truth is."""
    from booksmith.core.page import anchor, load_pages
    from booksmith.datasets import bench as bench_mod
    from booksmith.datasets.metrics import contour
    b, rd = _run_of(store, name, kind, label)
    if not b.truth_dir:
        raise Refusal(f"{name} has no truth: nothing to pair {kind}/{label} against")
    tdir = book.pages_dir(b.truth_dir, "truth")
    mdir = os.path.join(rd, "pages")
    t, m = _page_json(tdir, index, "truth"), _page_json(mdir, index, f"{kind}/{label}")
    # Whether the truth names its labelled pages is asked of the whole truth.
    said = contour.labelled_said(contour.labelled_of(load_pages(tdir, "truth")))
    res = contour.page_pairs(t, m, book.policy_beside(tdir), book.policy_beside(mdir),
                             said=said)
    pairs_ = list((res or {}).get("pairs", []))
    extras = list((res or {}).get("extras", []))
    if not truth_side:
        keep = ("run", "verdict", "label_ok", "fate")
        pairs_ = [{k: e[k] for k in keep} for e in pairs_]
        extras = [{"run": e["run"], "verdict": e["verdict"]} for e in extras]
    out: dict = {"index": index,
                 "labelled": bench_mod.trait_state(t.get("meta") or {}, "labelled"),
                 "compared": res is not None,
                 "pairs": pairs_,
                 "extras": extras}
    if truth_side:
        out["truth"] = [{"anchor": anchor(index, x["block_id"]), "block_id": x["block_id"],
                         "label": x["label"], "box": x["box"], "order": x.get("order")}
                        for x in t["blocks"]]
        out["out_of_scope"] = (t.get("meta") or {}).get("out_of_scope") or []
    return out


DPI_LEAST, DPI_MOST = 24.0, 300.0


@functools.lru_cache(maxsize=48)
def _render(pdf: str, sha: str, index: int, dpi: float) -> bytes:
    """One page of one scan at one dpi, kept. The key carries the manifest's
    hash, fixed once at upload and trusted after, as every reader of the
    book trusts it: a scan swapped under its manifest is not this cache's
    to notice."""
    from booksmith.core import raster
    with raster.open_pdf(pdf) as doc:
        if not 0 <= index < doc.page_count:
            raise Refusal(f"no page {index}: the scan has {doc.page_count}")
        return raster.render_png(doc[index], dpi)


def page_image(store: str, name: str, index: int, dpi: float = 110.0) -> bytes:
    """The scan's page as PNG at `dpi`, for the viewer to lay boxes over:
    the boxes are in the run's raster, and the viewer scales by the page's
    own width. Bounded, since a page at a thousand dpi is a memory ask."""
    b = book.Book.open(book_dir(store, name))
    if b.pdf is None:
        raise Refusal(f"{name}: the scan is not beside the manifest")
    if not DPI_LEAST <= dpi <= DPI_MOST:
        raise Refusal(f"dpi {dpi:g} is outside {DPI_LEAST:g}..{DPI_MOST:g}")
    return _render(os.path.realpath(b.pdf), b.sha256 or "", int(index), float(dpi))


def crop_png(store: str, name: str, kind: str, label: str, anchor: str,
             dpi: float | None = None) -> bytes:
    """One block as PNG. A read run keeps the crops it sent under `crops/`,
    and that file is the answer where it exists: what the model saw, not a
    second cut. Otherwise the box is cut from the book's own scan at `dpi`,
    else at the `CROP_DPI` the run's snapshot recorded, else at what the
    current job's knob says -- a viewer's cut, which the answer's caller
    should not mistake for the read's."""
    from booksmith.core import raster
    from booksmith.core.page import parse_anchor
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
    if dpi is not None and not DPI_LEAST <= dpi <= DPI_MOST:
        raise Refusal(f"dpi {dpi:g} is outside {DPI_LEAST:g}..{DPI_MOST:g}")
    if dpi is None:
        said = stamp.knob_values(book.snapshot_beside(os.path.join(rd, "pages")) or {})
        dpi = float(said["CROP_DPI"]) if said.get("CROP_DPI") else None
    with raster.open_pdf(b.pdf) as doc:
        png, _facts = raster.cut_png(doc, index, blk["box"], float(pg["dpi"]), dpi=dpi)
    return png


# --------------------------------------------------------------- measuring
def _pages_of(pdf: str | None, spec: str) -> list | None:
    """A page spec as `books detect` reads it, over the book's scan, or None
    for the whole book."""
    from booksmith.core import raster
    from booksmith.processing.layout.detect import parse_pages
    if not spec:
        return None
    if not pdf:
        raise Refusal("no scan to count pages against")
    with raster.open_pdf(pdf) as doc:
        return parse_pages(spec, doc.page_count)


def bench(store: str, path: str, settings: Mapping, run: str = "",
          kind: str = "detect", only: list | None = None,
          json_path: str | None = None, base: job.Job | None = None,
          pages: str = "") -> str:
    """Every applicable metric on one run of a book: one table printed, one
    JSON written under the store's `results/`. `pages` is a page spec as
    `books detect` takes it; a page set gets a results file of its own name,
    never the book's. Returns the JSON path."""
    from booksmith.datasets import table
    _inside(store, path)
    _inside(store, json_path)
    with _job(store, settings, "", base).active():
        b, r = open_book(path, kind, run)
        want = _pages_of(b.pdf, pages)
        recs = table.rows(b, r, only, want)
        table.render(recs)
        json_path = json_path or table.results_path(b, r, only, store, want)
        return table.write_json(recs, json_path, kind=r.level, pages=want)


def measure_page(store: str, name: str, kind: str, label: str, index: int,
                 only: list | None = None) -> list[dict]:
    """Every applicable metric's record for one page of a run, taken now
    and written nowhere: what a viewer shows beside the page."""
    from booksmith.datasets import table
    b, rd = _run_of(store, name, kind, label)
    bb, r = open_book(b.root, kind, label)
    with job.Job().active():
        return [rec.to_json() for rec in table.rows(bb, r, only, [int(index)])]


def results(store: str, name: str, kind: str, label: str) -> dict:
    """The records last written for a run, with each one's state against the
    run on disk: current, stale, not recorded. Refuses where nothing was
    measured, which is not a run with no numbers."""
    from booksmith.datasets import table
    from booksmith.datasets.metrics import base as metrics_base
    b, rd = _run_of(store, name, kind, label)
    bb, r = open_book(b.root, kind, label)
    path = table.results_path(bb, r, None, store)
    if not os.path.isfile(path):
        raise Refusal(f"{name} {kind}/{label} was not measured yet: no "
                      f"{os.path.relpath(path, store)}. Run a bench job first.")
    d = table.read_file(path)
    for rec in d["records"]:
        rec["state"] = metrics_base.staleness(rec.get("identity"), r.snapshot)
    d["path"] = os.path.relpath(path, store)
    return d


def selfcheck(store: str, path: str, run: str = "", kind: str = "detect",
              only: list | None = None, base: job.Job | None = None) -> dict:
    """Every applicable metric's probes on one bench and run: can the numbers
    fall. Returns the counts; `uncaught` is what a caller exits on."""
    from booksmith.datasets.metrics import BY_NAME, METRICS
    from booksmith.datasets.metrics import base as mbase
    _inside(store, path)
    with _job(store, {}, "", base).active():
        b, r = open_book(path, kind, run)
        pages = b.pages() if b.truth_dir else {}
        fit = mbase.applicable(METRICS, b, r, pages, r.pages())
        if only:
            unknown = [n for n in only if n not in BY_NAME]
            if unknown:
                raise Refusal(f"no metric named {', '.join(unknown)}; there are "
                              f"{', '.join(BY_NAME)}")
            off = [n for n in only if BY_NAME[n] not in fit]
            if off:
                raise Refusal(f"{', '.join(off)} cannot be measured on {b.name} "
                              f"with run {r.label}, so its probes say nothing")
            fit = [BY_NAME[n] for n in only]
        total = uncaught = mute = 0
        for i, metric in enumerate(fit, 1):
            job.current().check()
            probes = metric.probes(b, r)
            if not probes:
                log(f"{metric.name}: no probes on this run, nothing to knock out",
                    n=i, of=len(fit))
                continue
            seen, silent, bad = mbase.run_probes(probes)
            log(f"{metric.name}: probes {seen}, measured {seen - silent}, "
                f"nothing to measure with {silent}, uncaught {bad}",
                n=i, of=len(fit), probes=seen, uncaught=bad)
            total, uncaught, mute = total + seen, uncaught + bad, mute + silent
        applicable = mbase.applicable(METRICS, b, r, pages, r.pages())
        not_here = sorted(m.name for m in METRICS if m not in applicable)
        not_asked = sorted(m.name for m in applicable if m not in fit)
        log(f"{b.name} {r.label}: metrics {len(fit)}, probes {total}, "
            f"nothing to measure with {mute}, UNCAUGHT {uncaught}"
            + (f"; cannot be measured here: {', '.join(not_here)}" if not_here else "")
            + (f"; not selected: {', '.join(not_asked)}" if not_asked else ""))
        return {"metrics": len(fit), "probes": total, "mute": mute,
                "uncaught": uncaught, "not_here": not_here, "not_asked": not_asked}


def report(store: str, out: str | None = None) -> str:
    """Every record under the store's `results/` as one document, each
    checked against the run it describes under the store."""
    from booksmith.datasets import report as rendered
    return rendered.write(out or os.path.join(store, "METRICS.md"),
                          os.path.join(store, "results"), store)
