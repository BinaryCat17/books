"""Задача: PDF -> Markdown через PaddleOCR-VL на арендованной карте."""
import os

from booksmith.remote.spec import HostReq, JobSpec

HERE = os.path.dirname(os.path.abspath(__file__))

# Образ несёт только инструменты доставки (см. infra/base/Dockerfile), а
# python, CUDA, torch, vLLM и веса ставятся при старте скриптом provision.sh.
#
# Так вышло не из любви к сложности, а по замеру: docker качает три слоя
# одновременно, по одному потоку на слой, и реестр режет соединение до
# ~25 Мбит/с.  Итого 76 Мбит/с потолка при канале машины 1518 — образ на
# 6.02 ГБ ехал 10.7 минуты.  Те же 11 ГБ через uv и hf ставятся за 82
# секунды: они открывают десятки соединений и канал насыщают.
BASE_IMAGE = "ghcr.io/binarycat17/vast-base:1d35e99"
IMAGE_GB = 0.06
# Колёса плюс веса, как они едут по сети: 9.0 ГБ окружения на диске приезжают
# сжатыми колёсами, веса (2.2 ГБ) не сжимаются вовсе.  Замер: 82 секунды.
PAYLOAD_GB = 7.2

# Отдельного образа под Blackwell (sm_120) больше не нужно: раньше он был
# из-за колёс paddlepaddle-gpu под cu126, а детекция уехала на ONNX Runtime.

def spec(pdf: str, gpu: str = "RTX_4090", image: str | None = None,
         minutes: float = 20.0, budget_usd: float = 1.0,
         disk_gb: int = 60, max_dph: float = 0.60,
         machine_id: int | None = None) -> JobSpec:
    host = HostReq(gpu=gpu, disk_gb=disk_gb, max_dph=max_dph,
                   machine_id=machine_id)
    # Колёса torch — под CUDA 13, а значит нужен драйвер 580+.
    host.cuda_min = "13.0"

    return JobSpec(
        name=os.path.splitext(os.path.basename(pdf))[0][:40],
        image=image or BASE_IMAGE,
        command="bash run.sh input.pdf outputs",
        inputs={
            pdf: "input.pdf",
            os.path.join(HERE, "run.sh"): "run.sh",
            os.path.join(HERE, "provision.sh"): "provision.sh",
            os.path.join(HERE, "requirements.in"): "requirements.in",
            os.path.join(HERE, "entrypoint.py"): "entrypoint.py",
        },
        outputs="outputs",
        host=host,
        image_gb=IMAGE_GB,
        payload_gb=PAYLOAD_GB,
        minutes=minutes,
        budget_usd=budget_usd,
    )
