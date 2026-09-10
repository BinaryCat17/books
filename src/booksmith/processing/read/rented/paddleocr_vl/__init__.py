"""PaddleOCR-VL on a rented card: delivery, and the figures for ranking.

Only what the runner needs to pick a machine and price a run. The reading
itself lives in `readers/paddleocr_vl.py`, and no `Detector` belongs here --
this model reads, it does not detect layout.

`spec()` assembles the job. To the machine ride the book, the four job files
(`run.sh`, `provision.sh`, `constraints.txt`, `entrypoint.py`) and two
directories: the detect output we cut by, and `src/booksmith` itself. The
package rather than retyped code, so home and box run the same bytes.
"""
import os

import booksmith

from booksmith.remote.spec import HostReq, JobSpec
# The image this job runs in; `remote/image.py` owns both constants, so the
# sibling jobs cannot name two different machines.
from booksmith.remote.image import BASE_IMAGE, IMAGE_GB
from booksmith.core import knobs, stamp
from booksmith.core.errors import Refusal

HERE = os.path.dirname(os.path.abspath(__file__))
# The package root, `src/booksmith`, asked of the package itself: the working
# directory or a count of `dirname`s would ship emptiness or a partial package
# the moment this file moves.
PKG = os.path.dirname(os.path.abspath(booksmith.__file__))


# What crosses the wire: 9.0 GB of environment arrive as compressed wheels, the
# 2.2 GB of weights not compressed at all.
PAYLOAD_GB = 7.2

# Raising vLLM on a 5 GHz CPU -- imports, torch.compile, model warm-up, not the
# card itself; 374 s on a slower host.
WARMUP_S = 65.0

# The torch wheels are for CUDA 13, which needs driver 580+.
CUDA_MIN = "13.0"


def spec(pdf: str, detect_dir: str, pages: str = "",
         policy: str = "PP-DocLayoutV2", port: int = 8118,
         budget_usd: float = 0.60, timeout_minutes: float = 60.0) -> JobSpec:
    """The job for the runner: read a book's blocks on a rented card.

    All eight inputs are checked at home and for free -- the book, the detect
    pages and their snapshot, the four job files, the package -- because any one
    missing would otherwise surface on the rented card, for money.
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
            raise Refusal(f"no {p} ({what})")
    # The package must compile, and that is checked right before the upload.
    import compileall
    if not compileall.compile_dir(PKG, quiet=2, force=True):
        raise Refusal(
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
            # Without it provisioning falls two minutes after payment:
            # `provision.sh` installs from `$HERE/constraints.txt` under
            # `set -euo pipefail`.
            os.path.join(HERE, "constraints.txt"): "constraints.txt",
            os.path.join(HERE, "entrypoint.py"): "entrypoint.py",
        },
        outputs="outputs",
        # The crops are not pulled back: a local command cuts them out of the
        # book in seconds, and they outweigh all the rest together (167 MB of a
        # 179 MB directory).
        pull_exclude=("crops/",),
        image_gb=IMAGE_GB,
        payload_gb=PAYLOAD_GB,
        warmup_s=WARMUP_S,
        minutes=25.0,
        budget_usd=budget_usd,
        timeout_minutes=timeout_minutes,
        # What the operator set rides to the machine whole, taken from the
        # registry (`knobs.passthrough`) rather than typed by hand. A default is
        # never substituted here: the registry is its one place of residence.
        env={"HF_HUB_DISABLE_PROGRESS_BARS": "1",
             # The commit comes from here, git not being in the image; under
             # `passthrough`, so a hand-set value outweighs this guess.
             "BOOKSMITH_COMMIT": stamp.commit() or "",
             **knobs.passthrough()},
        host=HostReq(gpu="RTX_4090", disk_gb=60, max_dph=0.60,
                     # The CUDA requirement is the task's, see `CUDA_MIN`.
                     cuda_min=CUDA_MIN),
    )


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)
