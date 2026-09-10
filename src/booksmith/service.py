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
        raise Refusal(f"{path} lies outside the store {store}")
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


def upload(store: str, scan: str, name: str = "") -> str:
    """A scan into the store as a book: `processed/<name>/` with the scan
    beside its manifest, the hash taken once here and trusted after. A name
    already taken, or a scan the store already holds under another name, is
    refused: two books of one scan measure as one and read as two."""
    if not os.path.isfile(scan):
        raise Refusal(f"no file {scan}")
    stem = name or os.path.splitext(os.path.basename(scan))[0]
    safe = _SAFE.sub("-", stem).strip("-")[:80]
    if not safe:
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
    fname = os.path.basename(scan)
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
    the run lies in, else the store's `processed/`, unless named. Foreign
    work is not overwritten: a non-empty directory the builder did not make
    is a refusal out loud. Returns the build directory."""
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
                f"{out} already holds something not ours: neither "
                f"`{html_mod.ASSETS}/run.json` nor `run.json` in the root — so "
                f"the directory was not built by `books html`. Overwriting it "
                f"silently is not allowed: give --out or remove it by hand.")
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


# --------------------------------------------------------------- measuring
def bench(store: str, path: str, settings: Mapping, run: str = "",
          kind: str = "detect", only: list | None = None,
          json_path: str | None = None, base: job.Job | None = None) -> str:
    """Every applicable metric on one run of a book: one table printed, one
    JSON written under the store's `results/`. Returns the JSON path."""
    from booksmith.datasets import table
    _inside(store, path)
    _inside(store, json_path)
    with _job(store, settings, "", base).active():
        b, r = open_book(path, kind, run)
        recs = table.rows(b, r, only)
        table.render(recs)
        json_path = json_path or table.results_path(b, r, only, store)
        return table.write_json(recs, json_path, kind=r.level)


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
    """Every record under the store's `results/` as one document."""
    from booksmith.datasets import report as rendered
    return rendered.write(out or os.path.join(store, "METRICS.md"),
                          os.path.join(store, "results"))
