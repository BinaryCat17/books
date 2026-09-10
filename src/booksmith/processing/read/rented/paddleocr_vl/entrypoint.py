"""Reading blocks on a rented card. Executed on the box.

No rule is repeated here: the package itself travels (`spec()` sends
`src/booksmith` as an input file), and this file only fills in paths and calls
`booksmith.processing.read.driver`, so home and card run the same bytes.

Three things are local, all about the machine being someone else's: the path to
the book, which arrives as `input.pdf` while the detection snapshot remembers
the home one; the address of the vLLM brought up; and where the result goes. A
missing package, a missing detection directory or an endpoint answering with
another model's name fails before the first crop, the card ticking meanwhile.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="level two, on the box")
    ap.add_argument("--pkg", default=HERE,
                    help="where the booksmith package lies (it travels with the job)")
    ap.add_argument("--detect", required=True, help="a `books detect` directory")
    ap.add_argument("--pdf", required=True, help="the book as it landed on the box")
    ap.add_argument("--out", required=True)
    ap.add_argument("--server", required=True, help="the vLLM address, including /v1")
    ap.add_argument("--model", default="")
    ap.add_argument("--pages", default="")
    ap.add_argument("--policy", default="PP-DocLayoutV2")
    # `run.sh` passes this when `RESUME=0`, `RESUME` being a registry knob
    # forwarded by `knobs.passthrough()`; the flag and `read_book(resume=...)`
    # are the two halves of that one knob.
    ap.add_argument("--no-resume", action="store_true",
                    help="ask again even for what has already been read")
    a = ap.parse_args(argv)

    # The package is looked for explicitly and the failure is loud: otherwise an
    # `ImportError` arrives from the middle of the pass, on the money.
    if a.pkg not in sys.path:
        sys.path.insert(0, a.pkg)
    try:
        from booksmith.processing.read.transports import openai_http as vhttp
        from booksmith.processing.read import driver as vread
    except ImportError as e:
        raise SystemExit(
            f"the booksmith package will not import from {a.pkg}: {e}. It "
            f"travels as an input file of the job (`spec()` is beside this); "
            f"without it there is nothing to count with, and saying so now "
            f"beats saying it in the middle of the book.")

    if not os.path.isdir(os.path.join(a.detect, "pages")):
        raise SystemExit(f"no pages/ in {a.detect}: the detection directory did "
                         f"not arrive")

    # The address and the model name go through the environment, because the
    # transport reads them from the knob registry: a knob read around it does
    # not reach the snapshot, and the run becomes silently unrepeatable.
    os.environ["VLM_ENDPOINT"] = a.server
    if a.model:
        os.environ["MODEL_NAME"] = a.model

    reader = vread.build_reader(a.policy)
    transport = vhttp.build()
    who = transport.check()
    log(f"endpoint {who['endpoint']}: answers {who['models_on_server']}, "
        f"we ask for {who['asking_for']} -- they agree")

    pages = None
    if a.pages and a.pages != "-":
        import pymupdf
        from booksmith.processing.layout.detect import parse_pages
        with pymupdf.open(a.pdf) as d:
            pages = set(parse_pages(a.pages, d.page_count))

    t = vread.read_book(a.detect, a.out, reader, transport,
                        resume=not a.no_resume,
                        pages_want=pages, log=log, pdf=a.pdf)
    vread.report(t, log=log)
    vread.snapshot(a.detect, a.out, reader, transport, t,
                   {"detect": a.detect, "out": a.out, "pages": a.pages,
                    "on_box": True})
    # A quantity, not "done": it shows what was paid for.
    log(f"total: read {t['read']} of {t['asked']} asked, "
        f"chars {t['chars']}, compute {t['compute_seconds']:.0f} s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # A refusal from the package is one line and exit 1, as at home. The
        # class is imported here because this script starts before `--pkg` is on
        # `sys.path`; if the package will not import, the traceback is evidence.
        try:
            from booksmith.core.errors import BooksmithError
        except ImportError:
            raise e from None
        if isinstance(e, BooksmithError):
            print(f"{type(e).__name__}: {e}", flush=True)
            sys.exit(1)
        raise
