"""dots.ocr на арендованной карте: РЕЖИМ «ТОЛЬКО МАКЕТ».

Зачем платить за эту модель, когда шесть местных бесплатны. Замер на стенде
показал: шесть архитектур на процессоре — RT-DETR-L, RT-DETR с масками,
RT-DETR-L предыдущего поколения, RT-DETRv2, D-FINE и YOLOX — на странице с
двумя таблицами, разнесёнными на 164 пикселя чистой бумаги, НИ РАЗУ не
отдали две рамки. Авторы dots.ocr прямо пишут, что чинят обучением ровно это:
«без надзора за порядком чтения модель не воспринимает границы и неверно
объединяет отдельные элементы в одну рамку». Утверждение проверяемое, и у нас
есть чем: `bench/hard` — 130 страниц, 887 пар «два артефакта одного ярлыка
бок о бок», из них 124 страницы настоящие, с истиной от библиотекарей.

ЧТО ИМЕННО ЗАПУСКАЕТСЯ. Промт `prompt_layout_only_en` из карточки модели:
рамки и категории, БЕЗ распознавания текста. Категории — те же одиннадцать
DocLayNet, что у YOLOX, то есть политика ярлыков в проекте уже объявлена.
Текст не читается нарочно: мы меряем контуры, а чтение стоило бы вдесятеро
дороже и внесло бы вторую переменную.

ДРЕЙФ МЕРЯЕТСЯ ЗДЕСЬ ЖЕ. Детектор при тех же весах и входе даёт тот же
ответ; порождающая модель — не обязана. Публичного замера дрейфа РАМОК между
прогонами не нашлось ни одного (агенты искали). Поэтому после основного
прохода те же страницы гоняются ещё дважды, и расхождение считается числом.

ДЕНЬГИ. Потолок задан жёстко и мал: `budget_usd` и `timeout_minutes` — та
самая граница, при достижении которой машина гибнет, что бы ни шло.
"""
import os

from ..paddleocr_vl import BASE_IMAGE, IMAGE_GB
from ...remote.spec import HostReq, JobSpec

HERE = os.path.dirname(os.path.abspath(__file__))
# Веса 3B в bf16 — около 6 ГБ. Едут мимо docker, через hf, поэтому считаются
# отдельным полем: тот же гигабайт здесь занимает вдесятеро меньше времени.
PAYLOAD_GB = 6.2


def spec(pdf: str, pages: str = "", repeats: int = 1,
         budget_usd: float = 0.60, timeout_minutes: float = 60.0) -> JobSpec:
    """Задание для раннера. Ничего про OCR раннер не знает и знать не должен."""
    if not os.path.exists(pdf):
        raise SystemExit(f"нет {pdf}")
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
        # Прогрев: поставить колёса и скачать веса. Величина приведена к 5 ГГц,
        # как и у соседнего задания: упирается она в процессор, а не в карту.
        warmup_s=900.0,
        minutes=25.0,
        budget_usd=budget_usd,
        timeout_minutes=timeout_minutes,
        env={"HF_HUB_DISABLE_PROGRESS_BARS": "1"},
        host=HostReq(gpu="RTX_4090", disk_gb=60, max_dph=0.60),
    )
