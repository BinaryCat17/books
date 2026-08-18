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

ARG CUDA_TAG=12.9.1-base-ubuntu24.04
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

# --- слой 3: библиотеки CUDA отдельно от torch (~1.5 ГБ) ------------------
# Ставим их своей командой, чтобы они не слиплись с torch в один кусок.
RUN uv pip install --break-system-packages \
        nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12 \
        nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cusolver-cu12 \
        nvidia-cusparse-cu12 nvidia-nccl-cu12

# --- слой 4: torch (~1 ГБ поверх уже поставленных библиотек) --------------
ARG TORCH_BACKEND=auto
RUN uv pip install --break-system-packages --torch-backend=${TORCH_BACKEND} torch

# --- слой 5: vLLM (~0.5 ГБ) ----------------------------------------------
# PaddleOCR-VL поддержан в vLLM нативно начиная с 0.11.1; отдельный
# genai_server от Baidu не нужен.
ARG VLLM_VERSION=0.27.1
RUN uv pip install --break-system-packages "vllm==${VLLM_VERSION}"

# --- слой 6: paddle (~0.2 ГБ на CPU, ~3.7 ГБ на GPU) ----------------------
# По умолчанию CPU: на GPU считает vLLM, а paddle нужен только детекции
# макета (PP-DocLayoutV2, модель на 212 МБ). Разница в размере образа
# двадцатикратная. Если детекция на CPU окажется узким местом — пересобрать с
# PADDLE_PKG="paddlepaddle-gpu==3.2.1" и PADDLE_INDEX на индекс cu126.
ARG PADDLE_PKG=paddlepaddle==3.3.1
ARG PADDLE_INDEX=
RUN if [ -n "${PADDLE_INDEX}" ]; then \
        uv pip install --break-system-packages "${PADDLE_PKG}" -i "${PADDLE_INDEX}"; \
    else \
        uv pip install --break-system-packages "${PADDLE_PKG}"; \
    fi

# --- слой 7: PaddleOCR (~0.1 ГБ) -----------------------------------------
ARG PADDLEOCR_VERSION=3.7.0
RUN uv pip install --break-system-packages \
        "paddleocr[doc-parser]==${PADDLEOCR_VERSION}" pymupdf

# --- слой 8: веса (~2.1 ГБ) ----------------------------------------------
# Отдельным слоем намеренно: меняются независимо от кода и тянутся параллельно
# с ним. HF_HUB_ENABLE_HF_TRANSFER больше не работает — всё идёт через Xet.
ARG BAKE_WEIGHTS=1
ARG VL_MODEL=PaddlePaddle/PaddleOCR-VL-1.6
ARG LAYOUT_MODEL=PaddlePaddle/PP-DocLayoutV2
RUN if [ "${BAKE_WEIGHTS}" = "1" ]; then \
      uv pip install --break-system-packages "huggingface_hub>=1.28" && \
      hf download ${VL_MODEL}     --local-dir /models/vl && \
      hf download ${LAYOUT_MODEL} --local-dir /models/layout; \
    fi

ENV VL_MODEL_DIR=/models/vl \
    LAYOUT_MODEL_DIR=/models/layout \
    PATH=/usr/local/bin:$PATH

WORKDIR /root
CMD ["sleep", "infinity"]
