"""Задача: PDF -> Markdown через olmOCR-2-7B на арендованной карте.

Вторая задача рядом с paddleocr, а не замена ей: обе кладут результат в
одинаковую раскладку каталогов, чтобы bench/ можно было сравнивать напрямую.

Что за модель.  olmOCR-2-7B-1025 (Allen AI, arXiv 2510.19817) — дообученная
Qwen2.5-VL-7B-Instruct, лицензия Apache 2.0 и у весов, и у кода.  Читает
страницу ЦЕЛИКОМ по картинке: ни детектора макета, ни текстового слоя PDF ей
не нужно — document anchoring остался в первой версии olmOCR.  Отвечает
markdown с блоком front matter сверху; таблицы отдаёт в HTML, формулы в
LaTeX.  То, что таблицы именно HTML, для нас существенно: значит, <table> и
<td> считаются тем же способом, что у PaddleOCR-VL, и цифры сравнимы.
"""
import os

from booksmith.remote.spec import HostReq, JobSpec

HERE = os.path.dirname(os.path.abspath(__file__))

# Тот же образ-прихожая, что у paddleocr: в нём только инструменты доставки,
# всё остальное ставит provision.sh при старте.  Причина в infra/base/Dockerfile.
BASE_IMAGE = "ghcr.io/binarycat17/vast-base:d69de6e"
IMAGE_GB = 0.06

# Колёса плюс веса, как они едут по сети.  Дерево здесь короче, чем у
# paddleocr (197 пакетов против 241: нет ни paddle, ни onnxruntime), это
# около 4.6 ГБ колёс, зато веса весят 16.6 ГБ против 2.2 — bf16-модель на 7B
# против 0.9B.  Итого впятеро больше трафика при старте, и именно поэтому
# машину надо выбирать по каналу: на 1100 Мбит/с это две с половиной минуты,
# на 76 Мбит/с (как качает docker) — тридцать семь.
PAYLOAD_GB = 21.2

# Подъём vLLM.  Оценка, а не замер: у paddleocr на модели в 0.9B замерено 128с
# на процессоре в 5 ГГц, здесь к тому же добавляется чтение 15.5 ГиБ весов с
# диска.  После первого прогона цифру надо взять из журнала (books ledger,
# поле vllm_startup_s) и поправить здесь.
WARMUP_S = 180.0

# Веса в bf16, а не в FP8 (штатное умолчание olmocr — FP8).  Почему именно
# так — в шапке provision.sh: FP8_DYNAMIC требует sm_89, а сравнивать с
# PaddleOCR-VL надо в той же точности.  Переключается переменной окружения,
# перекомпиляция ничего не требует.
MODEL_REPO = "allenai/olmOCR-2-7B-1025"


def spec(pdf: str, gpu: str = "RTX_4090", image: str | None = None,
         minutes: float = 20.0, budget_usd: float = 1.0,
         disk_gb: int = 60, max_dph: float = 0.60,
         machine_id: int | None = None,
         model_repo: str | None = None,
         concurrency: int | None = None) -> JobSpec:
    host = HostReq(gpu=gpu, disk_gb=disk_gb, max_dph=max_dph,
                   machine_id=machine_id)
    # Колёса torch — под CUDA 13, а значит нужен драйвер 580+.
    host.cuda_min = "13.0"

    env = {"OLMOCR_MODEL_REPO": model_repo or MODEL_REPO}
    if concurrency:
        env["OLMOCR_CONCURRENCY"] = str(concurrency)

    return JobSpec(
        name="olmocr-" + os.path.splitext(os.path.basename(pdf))[0][:32],
        image=image or BASE_IMAGE,
        command="bash run.sh input.pdf outputs",
        inputs={
            pdf: "input.pdf",
            os.path.join(HERE, "run.sh"): "run.sh",
            os.path.join(HERE, "provision.sh"): "provision.sh",
            os.path.join(HERE, "constraints.txt"): "constraints.txt",
            os.path.join(HERE, "entrypoint.py"): "entrypoint.py",
        },
        outputs="outputs",
        env=env,
        host=host,
        image_gb=IMAGE_GB,
        payload_gb=PAYLOAD_GB,
        warmup_s=WARMUP_S,
        minutes=minutes,
        budget_usd=budget_usd,
    )
