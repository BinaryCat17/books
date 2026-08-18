"""Задача: PDF -> Markdown через PaddleOCR-VL на арендованной карте."""
import os

from booksmith.remote.spec import HostReq, JobSpec

HERE = os.path.dirname(os.path.abspath(__file__))

# Baidu отдаёт образ из Пекина одним потоком; наше зеркало приходит с ближайшей
# точки GHCR.  Размер и раскладка слоёв прочитаны из манифеста: 5.91 ГБ,
# 15 слоёв, из них paddlepaddle-gpu 3.69 ГБ и веса 1.54 ГБ.
REGISTRY = "ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle"
MIRROR = "ghcr.io/binarycat17"

IMAGES = {
    # Пока по умолчанию — зеркало официального образа: оно проверено в бою.
    # В нём НЕТ vllm, поэтому VLM считается в процессе и медленно.
    "mirror": f"{MIRROR}/paddleocr-vl:offline",
    # Наш образ (infra/image/Dockerfile): vLLM + пайплайн, слои примерно по
    # гигабайту.  Станет значением по умолчанию, когда пройдёт первый прогон
    # на bench/test25.pdf.  Требует драйвер под CUDA 13.
    "vllm": f"{MIRROR}/paddleocr-vl-vllm:latest",
    "source": f"{REGISTRY}/paddleocr-vl:latest-nvidia-gpu-offline",
    # Blackwell (sm_120): официальные колёса paddlepaddle собраны под cu126 и
    # sm_120 не содержат, поэтому для 5090 нужен отдельный образ.
    "sm120": f"{REGISTRY}/paddleocr-vl:latest-nvidia-gpu-sm120",
}
BLACKWELL = ("RTX_5090", "RTX_5080", "RTX_5070", "B200", "RTX_PRO_6000")
IMAGE_GB = 5.91


# Наш образ несёт torch с колёсами CUDA 13 — ему нужен драйвер 580+.
CUDA13_IMAGES = ("paddleocr-vl-vllm",)


def spec(pdf: str, gpu: str = "RTX_4090", image: str | None = None,
         minutes: float = 20.0, budget_usd: float = 1.0,
         disk_gb: int = 60, max_dph: float = 0.60,
         machine_id: int | None = None) -> JobSpec:
    if image is None:
        image = IMAGES["sm120"] if gpu in BLACKWELL else IMAGES["mirror"]
    host = HostReq(gpu=gpu, disk_gb=disk_gb, max_dph=max_dph,
                   machine_id=machine_id)
    if any(tag in image for tag in CUDA13_IMAGES):
        host.cuda_min = "13.0"

    return JobSpec(
        name=os.path.splitext(os.path.basename(pdf))[0][:40],
        image=image,
        command="bash run.sh input.pdf outputs",
        inputs={
            pdf: "input.pdf",
            os.path.join(HERE, "run.sh"): "run.sh",
            os.path.join(HERE, "entrypoint.py"): "entrypoint.py",
        },
        outputs="outputs",
        host=host,
        image_gb=IMAGE_GB,
        minutes=minutes,
        budget_usd=budget_usd,
    )
