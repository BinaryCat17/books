"""dots.ocr on a rented card, layout-only mode: a spec, not yet a command.

In: a PDF and a page selection. Out: boxes and DocLayNet categories per page,
no text -- the `prompt_layout_only_en` prompt of the model card. The word
`dots` appears in no CLI command; `spec()` is called by nothing and waits for
a model selector.

`budget_usd` and `timeout_minutes` are the line at which the machine dies,
whatever is still running. `DOTS_DIR` and `DOTS_MAX_PIXELS` are read in the
shell scripts, past `core/knobs.py`, so a run using them is unrepeatable.
"""
import os

from booksmith.remote.image import BASE_IMAGE, IMAGE_GB
from booksmith.remote.spec import HostReq, JobSpec
from booksmith.core.errors import Refusal

HERE = os.path.dirname(os.path.abspath(__file__))
# 3B weights in bf16, counted apart from the image: the hf route is ten times faster per GB.
PAYLOAD_GB = 6.2


def spec(pdf: str, pages: str = "", repeats: int = 1,
         budget_usd: float = 0.60, timeout_minutes: float = 60.0) -> JobSpec:
    """A job for the runner. The runner knows nothing about OCR, by design."""
    if not os.path.exists(pdf):
        raise Refusal(f"no such file: {pdf}")
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
        # Wheels and weights, normalised to 5 GHz: the warm-up is CPU-bound.
        warmup_s=900.0,
        minutes=25.0,
        budget_usd=budget_usd,
        timeout_minutes=timeout_minutes,
        env={"HF_HUB_DISABLE_PROGRESS_BARS": "1"},
        host=HostReq(gpu="RTX_4090", disk_gb=60, max_dph=0.60),
    )
