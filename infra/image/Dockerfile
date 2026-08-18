# PaddleOCR-VL + vLLM в одном контейнере.
#
# Зачем свой образ. Baidu намеренно разносит пайплайн и VLM по двум контейнерам
# docker compose, а инстанс vast.ai — это один контейнер. В официальном образе
# пайплайна vllm и torch нет вовсе (проверено по истории слоёв: там только
# paddlepaddle-gpu), поэтому VLM считался в процессе и еле полз.
#
# Раскладка слоёв здесь — не косметика. У официального образа один слой на
# 3.69 ГБ (62% объёма) и второй на 1.54 ГБ (26%): docker тянет слои по три, но
# внутри слоя идёт одно соединение, поэтому два слоя = два потока, и распаковка
# gzip тоже однопоточная на слой. Установки разнесены так, чтобы ни один слой
# не превышал примерно гигабайта. После первой сборки проверить фактическую
# раскладку: docker history --no-trunc <образ>

# CUDA 13: torch 2.13 несёт колёса nvidia-*-cu13, база должна совпадать.
# Требует драйвер 580+, поэтому офферы под этот образ фильтруются
# по cuda_vers>=13.0 (см. jobs/paddleocr).
ARG CUDA_TAG=13.0.1-base-ubuntu24.04
FROM nvidia/cuda:${CUDA_TAG}

# Колёса torch и paddle несут свои библиотеки CUDA, поэтому базовым берётся
# -base (0.14 ГБ), а не -runtime (2.44 ГБ): -runtime дублировал бы то, что и
# так приезжает в site-packages.

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    HF_HOME=/models/hf

# --- слой 1: система (~0.3 ГБ) -------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip \
        ca-certificates curl git rsync \
        libgl1 libglib2.0-0 fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3

# --- слой 2: uv (~0.05 ГБ) -----------------------------------------------
# uv ставит колёса параллельно; на 4 ГБ зависимостей это заметно быстрее pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# --- слой 3: полное закрепление версий ------------------------------------
# Ключевой шаг. Ставить пакеты по частям МОЖНО только если версии закреплены
# заранее: иначе следующая часть переустанавливает предыдущую, а удалённые
# файлы остаются в нижнем слое навсегда. В первой сборке так и вышло —
# torch снёс поставленные до него cudnn/nccl/cusparselt и скачал свои версии,
# и слой на 1.48 ГБ (16% образа) оказался оплачен ни за что.
COPY requirements.in /tmp/requirements.in
RUN uv pip compile --quiet /tmp/requirements.in -o /tmp/constraints.txt \
    && wc -l /tmp/constraints.txt

# Дальше — разбиение по слоям примерно по гигабайту. Критерий не «поменьше»:
# docker тянет три слоя параллельно, но внутри слоя идёт один поток, поэтому
# время выкачивания = max(крупнейший слой, весь объём / 3). Пока крупнейший
# больше трети объёма, он и есть узкое место. Размеры взяты из лога первой
# сборки, где uv напечатал вес каждого колеса.

# --- слой 4: библиотеки CUDA, часть 1 (~0.59 ГБ) --------------------------
RUN uv pip install --break-system-packages -c /tmp/constraints.txt \
        nvidia-cudnn-cu13 nvidia-cufft nvidia-nvjitlink

# --- слой 5: библиотеки CUDA, часть 2 (~0.55 ГБ) --------------------------
RUN uv pip install --break-system-packages -c /tmp/constraints.txt \
        nvidia-nccl-cu13 nvidia-cusolver nvidia-cusparselt-cu13 \
        nvidia-nvshmem-cu13

# --- слой 6: torch и triton (~0.69 ГБ) ------------------------------------
# БЕЗ --torch-backend: `auto` смотрит на драйвер СБОРОЧНОЙ машины, а у раннера
# GitHub видеокарты нет, и он молча ставит сборку +cpu. Колесо torch с PyPI
# и так собрано с CUDA.
RUN uv pip install --break-system-packages -c /tmp/constraints.txt \
        torch triton

# --- слой 7: тяжёлые довески vLLM (~1.5 ГБ) -------------------------------
# vLLM тянет 167 пакетов, включая компилятор CUDA (nvcc, nvvm, crt) и cutlass.
# Вынесены отдельно, иначе всё это слипается с самим vllm в один кусок.
RUN uv pip install --break-system-packages -c /tmp/constraints.txt \
        flashinfer-python nvidia-cutlass-dsl \
        nvidia-cuda-nvcc nvidia-nvvm nvidia-cuda-crt

# --- слой 8: сам vLLM и остаток его зависимостей (~1.0 ГБ) ----------------
RUN uv pip install --break-system-packages -c /tmp/constraints.txt vllm

# --- слой 9: движок детекции макета (~0.4 ГБ) -----------------------------
# Здесь стояла GPU-сборка paddle на 3.69 ГБ, и вот почему её больше нет.
#
# paddle нужен только детекции макета (PP-DocLayoutV2) — сам VLM считает vLLM.
# Замерено на реальных страницах книги, 5 страниц, 82 рамки:
#
#   paddle (CPU)        8.59 с/стр
#   ONNX Runtime (CPU)  2.45 с/стр      втрое быстрее на том же процессоре
#   совпадение выхода:  82/82 рамок, IoU 1.0000, расхождение координат 0.00 px
#
# Совпадение точное, а не «в пределах погрешности»: это перезапись графа, а не
# пересчёт весов. Официальные ONNX-веса весят 204.1 МБ против 203.9 МБ у
# paddle-версии — размер совпадает, значит конвертация без квантования.
# Квантованные версии на HF есть (uint8) — их брать нельзя.
#
# Два следствия помимо размера:
#   * onnxruntime-gpu 1.29 зависит от nvidia-cuda-runtime~=13.0 и
#     nvidia-cudnn-cu13 — ТОТ ЖЕ стек CUDA, что приносит torch. Уходит
#     сожительство cu126 и cu13 в одном контейнере;
#   * ONNX — приоритетный путь самого вендора для малых моделей: у PaddlePaddle
#     37 официальных ONNX-репозиториев (макет, ориентация, PP-OCRv5/v6,
#     формулы). Для самой VL-модели ONNX нет вовсе — там GGUF и vLLM.
#
# paddlepaddle CPU остаётся как каркас paddlex: сам вывод идёт через ORT.
# Откат на прежний вариант — сменой двух ARG, см. LAYOUT_ENGINE в workflow.
ARG PADDLE_PKG=paddlepaddle==3.3.1
ARG PADDLE_INDEX=
ARG ORT_PKG=onnxruntime-gpu==1.29.0
RUN if [ -n "${PADDLE_INDEX}" ]; then \
        uv pip install --break-system-packages "${PADDLE_PKG}" -i "${PADDLE_INDEX}"; \
    else \
        uv pip install --break-system-packages -c /tmp/constraints.txt "${PADDLE_PKG}"; \
    fi
RUN if [ -n "${ORT_PKG}" ]; then \
        uv pip install --break-system-packages -c /tmp/constraints.txt "${ORT_PKG}"; \
    fi

# --- слой 10: PaddleOCR (~0.1 ГБ) -----------------------------------------
ARG PADDLEOCR_VERSION=3.7.0
RUN uv pip install --break-system-packages -c /tmp/constraints.txt \
        "paddleocr[doc-parser]==${PADDLEOCR_VERSION}" pymupdf

# --- слой 11: веса (~2.1 ГБ) ----------------------------------------------
# Отдельным слоем намеренно: меняются независимо от кода и тянутся параллельно
# с ним. HF_HUB_ENABLE_HF_TRANSFER больше не работает — всё идёт через Xet.
ARG BAKE_WEIGHTS=1
ARG VL_MODEL=PaddlePaddle/PaddleOCR-VL-1.6
# ONNX-веса детекции макета — официальные, от самой PaddlePaddle.
ARG LAYOUT_MODEL=PaddlePaddle/PP-DocLayoutV2_onnx
RUN if [ "${BAKE_WEIGHTS}" = "1" ]; then \
      uv pip install --break-system-packages -c /tmp/constraints.txt \
          "huggingface_hub>=1.28" && \
      hf download ${VL_MODEL} --local-dir /models/vl; \
    fi

# Отдельным слоем: качается параллельно с весами VLM, а не после них.
RUN if [ "${BAKE_WEIGHTS}" = "1" ]; then \
      hf download ${LAYOUT_MODEL} --local-dir /models/layout; \
    fi

# Проверка целостности: если какая-то часть переустановила чужую версию,
# закрепление не сработало — лучше узнать на сборке, чем на арендованной карте.
RUN uv pip check

ENV VL_MODEL_DIR=/models/vl \
    LAYOUT_MODEL_DIR=/models/layout \
    PADDLE_PDX_MODEL_SOURCE=huggingface \
    PATH=/usr/local/bin:$PATH

WORKDIR /root
CMD ["sleep", "infinity"]
