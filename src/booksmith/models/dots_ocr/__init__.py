"""dots.ocr on a rented card, LAYOUT-ONLY mode. NOT WIRED INTO THE CLI YET.

STATUS, so nobody reads capability as practice. The word `dots` does not
appear in `cli.py`; `spec()` below is called by nothing. It stays because it
will be launchable once a model selector exists, and because of what it
already proved -- see below. Until then this is a specification, not a
command.

WHY PAY FOR THIS MODEL WHEN SIX LOCAL ONES ARE FREE. It answers the project's
one open question. Six CPU architectures -- RT-DETR-L, RT-DETR with masks, the
previous RT-DETR-L, RT-DETRv2, D-FINE and YOLOX, three families and two
vendors -- on a page with two tables separated by 164 pixels of clean paper,
NOT ONCE returned two boxes. dots.ocr returned three. On the `hard36`
distillate it finds 37 % against the best local 21 % and merges 196 times
against 268-314. So the merge is a property of the model, not of the task, and
training fixes it.

WHAT IT IS NOT. Replacing level one with it was REJECTED, by measurement: over
all 600 golden pages, same input, it returns 675 objects without loss against
1025 for PP-DocLayoutV2 on a CPU -- it crops tighter than the truth and cuts
content -- it is ten times slower, fragments four times as often, and on 23
dense strips hits the answer-length ceiling.

WHAT RUNS. The `prompt_layout_only_en` prompt from the model card: boxes and
categories, NO text recognition. The categories are the same eleven DocLayNet
ones YOLOX uses, so the label policy is already declared. Text is left unread
on purpose: we are measuring contours, and reading would cost ten times more
and add a second variable.

DRIFT IS NOT MEASURED, AND THE PROSE HERE USED TO SAY IT WAS. A detector
returns the same answer for the same weights and input; a generative model is
under no such obligation, and no public measurement of BOX drift between runs
was found. The `repeats` argument exists for it -- but it defaults to 1, and
what lies in git is `pass0` alone, 1274 files of a single pass. The capability
is here; the measurement was never made.

WHAT IT COST, from `runs/ledger.jsonl`: 16 rentals named `dots-layout`, ONE
of which succeeded. The successful one cost $0.892; all sixteen together cost
$1.370. Quote the second number when asking what the measurement cost -- the
fifteen failures are two thirds of the bill, and the four traps that caused
them are written down in `run.sh`, `provision.sh` and `entrypoint.py`. That
record is the second reason this directory is kept.

MONEY. The ceiling is hard and small: `budget_usd` and `timeout_minutes` are
the line at which the machine dies, whatever is still running.

TWO KNOBS ARE READ PAST THE REGISTRY -- `DOTS_DIR` and `DOTS_MAX_PIXELS`, in
the shell scripts. A knob outside `run/knobs.py` does not reach the snapshot,
so a run using them is silently unrepeatable. Declaring them belongs with the
CLI branch, not before it.
"""
import os

from ..paddleocr_vl import BASE_IMAGE, IMAGE_GB
from ...remote.spec import HostReq, JobSpec

HERE = os.path.dirname(os.path.abspath(__file__))
# 3B weights in bf16, about 6 GB. They travel past docker, over hf, and so
# are counted in a field of their own: the same gigabyte takes a tenth of the
# time on this route.
PAYLOAD_GB = 6.2


def spec(pdf: str, pages: str = "", repeats: int = 1,
         budget_usd: float = 0.60, timeout_minutes: float = 60.0) -> JobSpec:
    """A job for the runner. The runner knows nothing about OCR, by design."""
    if not os.path.exists(pdf):
        raise SystemExit(f"no such file: {pdf}")
    return JobSpec(
        name="dots-layout",
        image=BASE_IMAGE,
        command=(f"bash run.sh input.pdf outputs "
                 f"{repeats} {pages or '-'}"),
        inputs={pdf: "input.pdf",
                os.path.join(HERE, "run.sh"): "run.sh",
                os.path.join(HERE, "provision.sh"): "provision.sh",
                os.path.join(HERE, "entrypoint.py"): "entrypoint.py"},
        outputs="outputs",
        image_gb=IMAGE_GB,
        payload_gb=PAYLOAD_GB,
        # Warm-up: install wheels and pull the weights. Normalised to 5 GHz,
        # like the neighbouring job -- it is bound by the CPU, not the card.
        warmup_s=900.0,
        minutes=25.0,
        budget_usd=budget_usd,
        timeout_minutes=timeout_minutes,
        env={"HF_HUB_DISABLE_PROGRESS_BARS": "1"},
        host=HostReq(gpu="RTX_4090", disk_gb=60, max_dph=0.60),
    )
