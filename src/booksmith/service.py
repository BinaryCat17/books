"""The service: what the CLI and the web share, one function per command.

A store is a root directory in the shape `core/book.py` declares, `bench/`
and `processed/` under it. A user owns one; the admin's is the repository
root. Ownership of a book, its runs and its truth is the store it lies in.
Every function takes the store and the settings of the run and works under a
job bound to them, on paths inside that store. A store other than the admin's
may run only a preset from the admin's `models.json`, or the registry's
defaults.

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
from collections.abc import Mapping

from booksmith.core import book, config, job, knobs, served
from booksmith.core.errors import Refusal
from booksmith.core.log import log

ADMIN = config.ROOT


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


def models() -> dict:
    """The presets the admin declared, checked."""
    path = os.path.join(ADMIN, "models.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return registry(json.load(f), path)


def _admin(store: str) -> bool:
    return os.path.abspath(store) == os.path.abspath(ADMIN)


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


def _inside(store: str, path: str) -> str:
    if not _admin(store) and not os.path.abspath(path).startswith(
            os.path.abspath(store) + os.sep):
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
    entry's: the process's own key is the operator's, not the tenant's."""
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


def books(store: str) -> list[str]:
    return book.Book.list(store)


def _level_one(store: str, target: str, settings: Mapping, pages: str | None,
               out: str | None, model: str, hybrid: bool) -> str:
    from booksmith.processing.layout import detect as level_one
    _inside(store, target)
    kind, suffix = ("read", ".hybrid") if hybrid else ("detect", ".detect")
    with _job(store, settings, model).active():
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
           out: str | None = None, model: str = "") -> str:
    """Level one over a book directory or a bare PDF. Returns the run
    directory: under the book as `detect/<label>/`, else beside the file."""
    return _level_one(store, target, settings, pages, out, model, hybrid=False)


def hybrid(store: str, target: str, settings: Mapping, pages: str | None = None,
           out: str | None = None, model: str = "") -> str:
    """Boxes and content in one call from a served hybrid model, filed as a
    read run with its own boxes: `read/<label>/` under the book, else beside
    the file. Returns the run directory."""
    return _level_one(store, target, settings, pages, out, model, hybrid=True)


def read(store: str, detect_dir: str, settings: Mapping, out: str | None = None,
         pages: str = "", policy: str = "", model: str = "") -> str:
    """Level two over a detect run, through `VLM_ENDPOINT`; `pages` as
    `books detect` counts them, from one. Returns the run directory,
    `<detect dir>.read` unless named."""
    from booksmith.core import raster
    from booksmith.processing.layout.detect import parse_pages
    from booksmith.processing.read import driver
    from booksmith.processing.read.transports import openai_http
    _inside(store, detect_dir)
    with _job(store, settings, model).active():
        out = out or (os.path.abspath(detect_dir).rstrip("/") + ".read")
        want = None
        if pages:
            with raster.open_pdf(book.pdf_of(detect_dir)) as d:
                want = set(parse_pages(pages, d.page_count))
        pol = driver.policy_for(detect_dir, policy, what="the paid run")
        os.makedirs(out, exist_ok=True)
        reader = driver.build_reader(pol)
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


def bench(store: str, path: str, settings: Mapping, run: str = "",
          kind: str = "detect", only: list | None = None,
          json_path: str | None = None) -> str:
    """Every applicable metric on one run of a book: one table printed, one
    JSON written under the store's `results/`. Returns the JSON path."""
    from booksmith.datasets import table
    _inside(store, path)
    with _job(store, settings).active():
        b, r = open_book(path, kind, run)
        recs = table.rows(b, r, only)
        table.render(recs)
        json_path = json_path or table.results_path(b, r, only, store)
        return table.write_json(recs, json_path, kind=r.level)


def report(store: str, out: str | None = None) -> str:
    """Every record under the store's `results/` as one document."""
    from booksmith.datasets import report as rendered
    return rendered.write(out or os.path.join(store, "METRICS.md"),
                          os.path.join(store, "results"))
