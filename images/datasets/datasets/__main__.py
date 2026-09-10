import argparse
import os

from datasets import job, knobs
from datasets.log import log


def main() -> None:
    p = argparse.ArgumentParser(prog="datasets")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("synth", help="draw a bench of the tree's own")
    q.add_argument("--book", default="slovar")
    q.add_argument("--out", required=True)
    q = sub.add_parser("annopage", help="a bench out of the AnnoPage corpus")
    q.add_argument("--root", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--split", default="")
    q.add_argument("--limit", type=int, default=0)
    q = sub.add_parser("subset", help="the hard pages of several benches as one")
    q.add_argument("--books", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--root", default=os.path.join(os.environ.get("BOOKSMITH_HOME") or ".", "bench"))
    a = p.parse_args()
    with job.Job(settings={k: v for k, v in os.environ.items() if k in knobs.names()}).active():
        if a.cmd == "synth":
            from datasets import synth

            synth.build(a.out, None, knobs.number("SYNTH_SEED", kind=int), knobs.knob("SYNTH_AGING"), book=a.book)
        elif a.cmd == "annopage":
            from datasets import annopage

            annopage.build(a.root, a.out, a.split or None, a.limit or None)
        else:
            from datasets import subset

            subset.build([b for b in a.books.split(",") if b], a.out, a.root)
    log(f"{a.cmd}: written to {a.out}")


main()
