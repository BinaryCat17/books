"""The service: what the CLI and the web share, one function per command.

A store is a root directory in the shape `core/book.py` declares, `bench/`
and `processed/` under it. A user owns one; the admin's is the repository
root. Ownership of a book, its runs and its truth is the store it lies in.
Every function takes the store and the settings of the run and works under a
job bound to them, on paths inside that store. A store other than the admin's
may run only a preset from the admin's `models.json`, `{name: {KNOB: value}}`,
or the registry's defaults: a model is a named set of knob values over the
adapters the tree has, and its fingerprint, label and identity stay the
adapter's.
"""
import dataclasses
import json
import os
from collections.abc import Mapping

from booksmith.core import book, config, job, knobs
from booksmith.core.errors import Refusal
from booksmith.core.log import log

ADMIN = config.ROOT


def models() -> dict:
    """The presets the admin declared."""
    path = os.path.join(ADMIN, "models.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _admin(store: str) -> bool:
    return os.path.abspath(store) == os.path.abspath(ADMIN)


def check(store: str, settings: Mapping, presets: Mapping | None = None) -> None:
    if _admin(store) or not settings:
        return
    presets = models() if presets is None else presets
    given = {k: str(v) for k, v in settings.items()}
    if given not in [{k: str(v) for k, v in p.items()} for p in presets.values()]:
        raise Refusal(
            f"{store}: these settings are not one of the presets "
            f"{sorted(presets) or 'the admin declared (there are none)'}; "
            f"a store other than the admin's runs a preset whole, or the "
            f"defaults.")


def _inside(store: str, path: str) -> str:
    if not _admin(store) and not os.path.abspath(path).startswith(
            os.path.abspath(store) + os.sep):
        raise Refusal(f"{path} lies outside the store {store}")
    return path


def _job(store: str, settings: Mapping) -> job.Job:
    check(store, settings)
    return dataclasses.replace(job.current(), settings=dict(settings))


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


def detect(store: str, target: str, settings: Mapping, pages: str | None = None,
           out: str | None = None) -> str:
    """Level one over a book directory or a bare PDF. Returns the run
    directory: under the book as `detect/<label>/`, else beside the file."""
    from booksmith.processing.layout import detect as level_one
    _inside(store, target)
    with _job(store, settings).active():
        if os.path.isfile(os.path.join(target, "manifest.json")):
            bk = book.Book.open(target, "detect")
            pdf = bk.pdf
            if pdf is None:
                raise Refusal(
                    f"{bk.name}: the manifest names "
                    f"{(bk.manifest.get('source') or {}).get('name')!r} and it is "
                    f"not beside the manifest. The book directory is where the "
                    f"scan lives; a run cannot be measured against a file that "
                    f"is not there.")
            # The label before the pages: building the adapter costs a session
            # load and no pages, so a run that cannot be filed refuses first.
            out = out or bk.run_dir("detect", level_one._adapter().label())
            target = pdf
        out = out or os.path.splitext(target)[0] + ".detect"
        return level_one.run(target, out, pages)


def read(store: str, detect_dir: str, settings: Mapping, out: str | None = None,
         pages: str = "", policy: str = "") -> str:
    """Level two over a detect run, through `VLM_ENDPOINT`; `pages` as
    `books detect` counts them, from one. Returns the run directory,
    `<detect dir>.read` unless named."""
    from booksmith.core import raster
    from booksmith.processing.layout.detect import parse_pages
    from booksmith.processing.read import driver
    from booksmith.processing.read.transports import openai_http
    _inside(store, detect_dir)
    with _job(store, settings).active():
        out = out or (os.path.abspath(detect_dir).rstrip("/") + ".read")
        want = None
        if pages:
            with raster.open_pdf(book.pdf_of(detect_dir)) as d:
                want = set(parse_pages(pages, d.page_count))
        policy_name = driver.policy_for(detect_dir, policy, what="the paid run")
        os.makedirs(out, exist_ok=True)
        reader = driver.build_reader(policy_name)
        transport = openai_http.build()
        who = transport.check()
        log(f"endpoint {who['endpoint']}: answers {who['models_on_server']}, "
            f"we ask {who['asking_for']} — matched")
        t = driver.read_book(detect_dir, out, reader, transport,
                             resume=knobs.knob("RESUME") == "1", pages_want=want)
        driver.report(t)
        p = driver.snapshot(detect_dir, out, reader, transport, t,
                            {"detect": detect_dir, "out": out, "pages": pages,
                             "policy": policy_name})
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
        return table.write_json(recs, json_path, kind=r.kind)


def report(store: str, out: str | None = None) -> str:
    """Every record under the store's `results/` as one document."""
    from booksmith.datasets import report as rendered
    return rendered.write(out or os.path.join(store, "METRICS.md"),
                          os.path.join(store, "results"))
