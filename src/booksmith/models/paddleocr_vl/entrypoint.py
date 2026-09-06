"""Reading blocks on a rented card. Executed ON the box.

NOT ONE RULE IS REPEATED HERE, and that is the main difference from the
neighbouring `dots_ocr/entrypoint.py`, which carries its own copy of the page
parser and says so about itself. The project has already paid for such a
divergence -- the knob registry against the job builder, 13 names of 17 --
and there is no reason to pay twice.

Instead of a copy, THE PACKAGE ITSELF travels: `spec()` sends `src/booksmith`
as an input file (1.1 MB against 6.2 GB of weights, a quantity that can be
ignored), and this file only fills in paths and calls `booksmith.read.run`.
So at home and on the card the SAME code runs, byte for byte, and it was
checked at home against a stand-in server -- free and in advance
(`tests/test_read.py`, 27 checks).

WHAT IS LOCAL RATHER THAN SHARED. Exactly three things, all three about the
machine being someone else's: the path to the book (it arrives as `input.pdf`
while the detection snapshot remembers the home path), the address of the
vLLM that was brought up, and where the result goes.

WHAT MUST FAIL HERE AND NOT HALFWAY. A missing package, a missing detection
directory, an endpoint answering with another model's name. Each of the three
costs exactly as much as the card ticks, so each is checked before the first
crop.
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
    # `run.sh` passes this flag when `RESUME=0`, and `RESUME` is a declared
    # registry knob forwarded by `knobs.passthrough()`. The flag did not exist
    # here at all, so an operator who set `RESUME=0` got `error: unrecognized
    # arguments: --no-resume`, exit code 2 -- AFTER the rental, the unrolling
    # and the vLLM coming up. The other half of the same defect: `resume` was
    # not passed to `read_book` either, so at `RESUME=1` the knob decided
    # nothing. It had no third behaviour.
    ap.add_argument("--no-resume", action="store_true",
                    help="ask again even for what has already been read")
    a = ap.parse_args(argv)

    # The package is looked for EXPLICITLY and the failure is loud: without
    # it an `ImportError` would come from the middle of the pass -- on the
    # money, and halfway.
    if a.pkg not in sys.path:
        sys.path.insert(0, a.pkg)
    try:
        from booksmith.read import http as vhttp
        from booksmith.read import run as vread
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
    # transport reads them from the knob registry. Nothing here goes past the
    # registry: a knob read around it does not reach the snapshot, and the run
    # becomes silently unrepeatable.
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
        from booksmith.detect import parse_pages
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
    sys.exit(main())
