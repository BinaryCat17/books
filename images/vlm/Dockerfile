FROM debian:12-slim
ARG COMMIT=""
ARG VL_REPO=PaddlePaddle/PaddleOCR-VL-1.6
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      curl ca-certificates libgl1 libglib2.0-0 libgomp1 gcc g++ libc6-dev procps \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
ENV UV_LINK_MODE=copy UV_HTTP_TIMEOUT=180 HF_HUB_DISABLE_PROGRESS_BARS=1
RUN uv python install 3.12 && uv venv /opt/env --python 3.12
ENV VIRTUAL_ENV=/opt/env PATH=/opt/env/bin:$PATH
COPY images/vlm/constraints.txt /tmp/constraints.txt
RUN uv pip install -r /tmp/constraints.txt --torch-backend=cu130 \
 && uv pip install -c /tmp/constraints.txt "huggingface_hub[cli]"
RUN hf download "$VL_REPO" --local-dir /models/vl \
 && printf '{"repo": "%s"}\n' "$VL_REPO" > /models/vl/SOURCE.json
WORKDIR /app
COPY images/vlm/pyproject.toml /app/
COPY images/vlm/vlm /app/vlm
COPY images/vlm/start.sh /app/start.sh
RUN uv pip install --no-deps . && chmod +x /app/start.sh
RUN python -c "from vlm.serve import weights_sha256; print(weights_sha256('/models/vl')[:12])"
ENV VL_MODEL_DIR=/models/vl BOOKSMITH_COMMIT=$COMMIT PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["/app/start.sh"]
