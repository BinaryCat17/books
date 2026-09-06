"""PaddleOCR-VL on a rented card: delivery, and the figures for ranking.

WHAT IS HERE: only what the runner needs to pick a machine and price a run.
The reading lives next door in `reader.py`; a `Recognizer` of `models.base`
is not here and will not be -- this model reads, it does not detect layout.
`books read` has ridden this spec: 436 pages over eight rentals ($0.545 by
`runs/ledger.jsonl`, two of them successful).

`spec()` below assembles the job. To the machine ride the book, the four job
files (`run.sh`, `provision.sh`, `constraints.txt`, `entrypoint.py`) and TWO
DIRECTORIES: the detect output (the boxes we cut by) and THE `src/booksmith`
PACKAGE ITSELF. The package instead of retyped code is a decision, not a
convenience: the neighbouring `dots_ocr/entrypoint.py` carries its own copy of
the page parser, and the two diverged on four inputs of thirteen before
`tests/test_parse_pages.py` held them. It weighs 1.2 MB of `.py`, 5.5 MB on
disk as it rides (`doc/mathjax`, fresh `__pycache__`), against 2.2 GB of
weights -- negligible, where a divergence of copies costs a run.
"""
import os

from ...remote.spec import HostReq, JobSpec
from ...run import knobs, stamp

HERE = os.path.dirname(os.path.abspath(__file__))
# The package root, `src/booksmith`. From here rather than from the working
# directory -- otherwise a job assembled elsewhere would carry emptiness.
PKG = os.path.dirname(os.path.dirname(HERE))

# The image carries only the delivery tools (see infra/base/Dockerfile);
# python, CUDA, torch, vLLM and the weights are installed at start by
# provision.sh.
#
# Not love of complexity but measurement: docker pulls three layers at once,
# one stream per layer, and the registry cuts a connection to ~25 Mbit/s. A
# 76 Mbit/s ceiling against the machine's 1518 -- a 6.02 GB image rode 10.7
# minutes. The same 11 GB through uv and hf install in 82 seconds: dozens of
# connections, and the channel saturated.
#
# Measured on our side and needing no ground truth: it is about the network,
# not parsing, and so survived the clean slate, unlike the table figures.
BASE_IMAGE = "ghcr.io/binarycat17/vast-base:d69de6e"
IMAGE_GB = 0.06

# Wheels plus weights as they travel the wire: 9.0 GB of environment on disk
# arrive as compressed wheels, the weights (2.2 GB) do not compress at all.
# Measured: 82 seconds.
PAYLOAD_GB = 7.2

# Raising vLLM on a 5 GHz CPU. Not the card: imports, torch.compile and the
# model warm-up. On a slower host it grew to 374 s.
WARMUP_S = 65.0

# The torch wheels are for CUDA 13, which needs driver 580+.
CUDA_MIN = "13.0"


def spec(pdf: str, detect_dir: str, pages: str = "",
         policy: str = "PP-DocLayoutV2", port: int = 8118,
         budget_usd: float = 0.60, timeout_minutes: float = 60.0) -> JobSpec:
    """The job for the runner: read a book's blocks on a rented card.

    WHAT IS CHECKED HERE, AT HOME AND FOR FREE: all eight inputs -- the book,
    the detect pages and their snapshot, the four job files, the package. Any
    one missing would otherwise surface on the rented card, for money; the
    previous level two was debugged exactly so -- thirteen launches, $0.52,
    two useful.
    """
    for p, what in ((pdf, "book"),
                    (os.path.join(detect_dir, "pages"), "detection pages"),
                    (os.path.join(detect_dir, "run.json"),
                     "detection snapshot"),
                    (os.path.join(HERE, "constraints.txt"),
                     "the pinned dependency tree"),
                    (os.path.join(HERE, "provision.sh"), "provisioning"),
                    (os.path.join(HERE, "run.sh"), "the run on the box"),
                    (os.path.join(HERE, "entrypoint.py"), "the box entry "
                     "point"),
                    (PKG, "the booksmith package")):
        if not os.path.exists(p):
            raise SystemExit(f"no {p} ({what})")
    # THE PACKAGE MUST COMPILE, AND THAT IS CHECKED RIGHT BEFORE THE UPLOAD.
    # Measured: during edits the tree failed to parse for half a minute
    # (`SyntaxError` in `read/run.py`), and in that window a book of code that
    # does not start would have ridden to the box -- learnt after a whole
    # rental of provisioning, weights and vLLM warm-up. The check costs a
    # fraction of a second.
    import compileall
    if not compileall.compile_dir(PKG, quiet=2, force=True):
        raise SystemExit(
            f"the package {PKG} does not compile whole -- a tree that will "
            f"not run would sail to the box, and we would learn it for money. "
            f"Sort out the error above and retry.")
    return JobSpec(
        name="vl-read",
        image=BASE_IMAGE,
        command=(f"bash run.sh input.pdf detect outputs {port} "
                 f"{shlex_quote(pages or '-')} {shlex_quote(policy)}"),
        inputs={
            pdf: "input.pdf",
            detect_dir: "detect",
            PKG: "booksmith",
            os.path.join(HERE, "run.sh"): "run.sh",
            os.path.join(HERE, "provision.sh"): "provision.sh",
            # WITHOUT IT PROVISIONING FALLS TWO MINUTES AFTER PAYMENT.
            # `provision.sh` installs the wheels with
            # `uv pip install -r "$HERE/constraints.txt"`, where `$HERE` is
            # its own directory on the box. The file was not listed in
            # `inputs`, and `set -euo pipefail` felled the script:
            #     error: File not found: `/root/job/constraints.txt`
            # Checked on an assembled box layout with stand-in `uv` and `hf`.
            os.path.join(HERE, "constraints.txt"): "constraints.txt",
            os.path.join(HERE, "entrypoint.py"): "entrypoint.py",
        },
        outputs="outputs",
        # The crops are NOT pulled back: a local command cuts them out of the
        # book in seconds, and they weigh more than all the rest together.
        # Measured on the neighbouring job: 167 MB of pictures out of a 179 MB
        # directory, at 2.9 Mbit/s -- sixteen minutes of transfer for nothing.
        pull_exclude=("crops/",),
        image_gb=IMAGE_GB,
        payload_gb=PAYLOAD_GB,
        warmup_s=WARMUP_S,
        minutes=25.0,
        budget_usd=budget_usd,
        timeout_minutes=timeout_minutes,
        # WHAT THE OPERATOR SET rides to the machine WHOLE, not by selection.
        # The list is built from the registry (`knobs.passthrough`), not typed
        # by hand: hand-typed it had already diverged, 13 names of 17, with
        # four knobs deciding the choice of weights never riding at all.
        # Defaults are NOT substituted: they have one place of residence, the
        # registry, and a second copy in `run.sh` would mean a changed default
        # never reaching the machine.
        env={"HF_HUB_DISABLE_PROGRESS_BARS": "1",
             # The commit comes from here: on the box there is no one to ask,
             # git is not in the image. Placed UNDER `passthrough`, so that
             # what the operator set by hand outweighs the builder's guess.
             "BOOKSMITH_COMMIT": stamp.commit() or "",
             **knobs.passthrough()},
        host=HostReq(gpu="RTX_4090", disk_gb=60, max_dph=0.60,
                     # The CUDA requirement is the TASK's, see `CUDA_MIN`.
                     cuda_min=CUDA_MIN),
    )


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)
