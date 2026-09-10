# PaddleOCR-VL behind the model protocol: vLLM with describe and health
# beside it, the chat route passed through unchanged.
#
# What the rented run script provisioned at every start is a layer here:
# python by uv, the whole pinned tree from constraints.txt, the weights from
# the 1.6 repository with SOURCE.json beside them. The image is large and
# pulled once; the market's argument against layers -- docker pulls three
# streams at a throttled registry -- weighs against a start that installed
# nine gigabytes every time. A CUDA driver comes from the host; the wheels
# carry the runtime.
#
#   docker build -f infra/models/paddleocr-vl/Dockerfile -t model-paddleocr-vl .
#   docker run --rm --gpus all -p 8000:8000 model-paddleocr-vl
#   VLM_ENDPOINT=http://127.0.0.1:8000/v1 books read <detect dir>
FROM debian:12-slim

ARG COMMIT=""
ARG VL_REPO=PaddlePaddle/PaddleOCR-VL-1.6

# The same packages the hallway image carries, for the same reasons written
# beside it in infra/base/Dockerfile: opencv's libGL, OpenMP, the host
# compiler triton and flashinfer call, procps for the group kill's sweep.
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      curl ca-certificates libgl1 libglib2.0-0 libgomp1 gcc g++ libc6-dev procps \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
ENV UV_LINK_MODE=copy UV_HTTP_TIMEOUT=180 HF_HUB_DISABLE_PROGRESS_BARS=1

RUN uv python install 3.12 && uv venv /opt/env --python 3.12
ENV VIRTUAL_ENV=/opt/env PATH=/opt/env/bin:$PATH

# The pinned tree, the same file the rented job installed; the version of
# uv above must be the one that built it (see the file's header).
COPY src/booksmith/processing/read/rented/paddleocr_vl/constraints.txt /tmp/constraints.txt
RUN uv pip install -r /tmp/constraints.txt --torch-backend=cu130 \
 && uv pip install "huggingface_hub[cli]"

# The 1.6 repository, and its name written beside the weights: config.json is
# byte-identical between releases, so the name is the only proof of which.
RUN hf download "$VL_REPO" --local-dir /models/vl \
 && printf '{"repo": "%s"}\n' "$VL_REPO" > /models/vl/SOURCE.json

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY infra/models/paddleocr-vl/start.sh /app/start.sh
RUN uv pip install --no-deps . && chmod +x /app/start.sh

ENV VL_MODEL_DIR=/models/vl \
    MODEL_NAME=PaddleOCR-VL-1.6-0.9B \
    PORT=8118 \
    VLLM_USE_FLASHINFER_SAMPLER=0 \
    BOOKSMITH_COMMIT=$COMMIT \
    PYTHONUNBUFFERED=1

EXPOSE 8000
ENTRYPOINT ["/app/start.sh"]
