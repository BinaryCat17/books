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

# --- слой 3: библиотеки CUDA отдельно от torch (~1.5 ГБ) ------------------
# Именно этот набор объявлен зависимостями torch 2.13.0 (сверено с метаданными
# PyPI).  Ставим их своей командой, чтобы они не слиплись с torch в один кусок;
# ошибиться в именах нельзя — лишние колёса осели бы в образе навсегда.
ARG TORCH_VERSION=2.13.0
RUN uv pip install --break-system-packages \
        nvidia-cudnn-cu13 nvidia-cusparselt-cu13 \
        nvidia-nccl-cu13 nvidia-nvshmem-cu13

# --- слой 4: torch (~1 ГБ поверх уже поставленных библиотек) --------------
# БЕЗ --torch-backend: `auto` определяет CUDA по драйверу СБОРОЧНОЙ машины, а у
# раннера GitHub видеокарты нет, и он молча ставит сборку +cpu — то есть образ
# уезжает без поддержки GPU, ради которой всё и затевалось.  Колесо torch с
# PyPI и так собрано с CUDA.
RUN uv pip install --break-system-packages "torch==${TORCH_VERSION}"

# --- слой 5: vLLM (~0.5 ГБ) ----------------------------------------------
# PaddleOCR-VL поддержан в vLLM нативно начиная с 0.11.1; отдельный
# genai_server от Baidu не нужен.
ARG VLLM_VERSION=0.27.1
RUN uv pip install --break-system-packages "vllm==${VLLM_VERSION}"

# --- слой 6: paddle (~3.7 ГБ) ---------------------------------------------
# По умолчанию GPU, и это ЗАМЕРЕНО, а не выбрано по осторожности.
# paddle нужен только детекции макета (PP-DocLayoutV2), сам VLM считает vLLM,
# поэтому напрашивался CPU-вариант: колесо 186 МБ против 3.69 ГБ. Замер на
# 16 ядрах, 150 dpi, реальные страницы книги:
#
#   по умолчанию          7.59 с/стр  ->  539 страниц = 68 мин
#   MKLDNN + 16 потоков   9.71 с/стр  ->  87 мин   (многопоточность ХУЖЕ)
#   MKLDNN + 8 потоков    8.26 с/стр  ->  74 мин
#
# Против ~8 минут работы самого VLM на карте. В деньгах: CPU-сборка выходит
# $0.449 за книгу против $0.097 у GPU-сборки — экономия четырёх гигабайт
# образа оборачивается лишним часом аренды.
#
# Цена решения: paddlepaddle-gpu собран под cu126, а torch несёт cu13, то есть
# в контейнере уживаются два поколения CUDA. Каждый несёт свои библиотеки,
# связующее звено — драйвер 580+, поэтому офферы фильтруются по cuda_vers>=13.0
# (проверено: рынок это не сужает, 29 офферов и так, и так).
#
# Версия 3.2.1 взята из официального образа Baidu, где она проверена в паре с
# paddleocr. Если paddleocr 3.7 потребует новее — поднять до 3.3.1, если она
# есть на индексе (проверить из сети, где paddlepaddle.org.cn доступен).
ARG PADDLE_PKG=paddlepaddle-gpu==3.2.1
ARG PADDLE_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu126/
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

# PADDLE_PDX_MODEL_SOURCE переключает paddlex на Hugging Face, чтобы он нашёл
# уже скачанные веса в HF_HOME, а не тянул их со своего CDN при первом запуске.
# ПРОВЕРИТЬ на первом же прогоне: в логе не должно быть загрузок моделей.
ENV VL_MODEL_DIR=/models/vl \
    LAYOUT_MODEL_DIR=/models/layout \
    PADDLE_PDX_MODEL_SOURCE=huggingface \
    PATH=/usr/local/bin:$PATH

WORKDIR /root
CMD ["sleep", "infinity"]
