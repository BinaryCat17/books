# One layout detector of the tree's own, behind the model protocol.
#
# One Dockerfile, one tag per detector: the build arguments name the weights
# repository, the directory the adapter looks in, the adapter and the model
# name, and the workflow in .github/workflows/models.yml lists the six.
# The weights are baked in at build, so a start is a pull and nothing else,
# and the image carries the detect extra alone: the shim is the standard
# library's server, and onnxruntime with opencv is what a detector needs.
#
#   docker build -f infra/models/layout-cpu/Dockerfile \
#     --build-arg MODEL_REPO=PaddlePaddle/PP-DocLayoutV2_onnx \
#     --build-arg MODEL_DIR=PP-DocLayoutV2_onnx \
#     --build-arg LAYOUT_ADAPTER=doclayout \
#     --build-arg LAYOUT_MODEL_NAME=PP-DocLayoutV2 \
#     -t model-pp-doclayoutv2 .
#   docker run --rm -p 8000:8000 model-pp-doclayoutv2
#   LAYOUT_ADAPTER=served LAYOUT_ENDPOINT=http://127.0.0.1:8000 books detect bench/slovar
FROM python:3.12-slim

ARG MODEL_REPO
ARG MODEL_DIR
ARG LAYOUT_ADAPTER
ARG LAYOUT_MODEL_NAME=""
# The commit this image was built from, for the snapshot of every run
# through it: the image carries no git.
ARG COMMIT=""

# libgl1 and libglib2.0-0 for opencv, libgomp1 for numpy and onnxruntime.
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      libgl1 libglib2.0-0 libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN uv pip install --system --no-cache ".[detect]" \
 && uv pip install --system --no-cache "huggingface_hub[cli]"

# Where the adapters look: paddlex's convention, kept so the same code runs
# here and on a developer's machine.
RUN hf download "$MODEL_REPO" --local-dir "/root/.paddlex/official_models/$MODEL_DIR"

ENV LAYOUT_ADAPTER=$LAYOUT_ADAPTER \
    LAYOUT_MODEL_NAME=$LAYOUT_MODEL_NAME \
    BOOKSMITH_COMMIT=$COMMIT \
    PYTHONUNBUFFERED=1

EXPOSE 8000
ENTRYPOINT ["books", "serve", "layout", "--host", "0.0.0.0", "--port", "8000"]
