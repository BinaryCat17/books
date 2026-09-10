FROM python:3.12-slim
ARG MODEL_REPO
ARG MODEL_DIR
ARG LAYOUT_ADAPTER=doclayout
ARG LAYOUT_MODEL_NAME=""
ARG COMMIT=""
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libgl1 libglib2.0-0 libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
RUN uv pip install --system --no-cache "huggingface_hub[cli]"
RUN hf download "$MODEL_REPO" --local-dir "/root/.paddlex/official_models/$MODEL_DIR"
WORKDIR /app
COPY schema /app/schema
COPY images/layout/pyproject.toml /app/
COPY images/layout/layout /app/layout
RUN uv pip install --system --no-cache .
ENV LAYOUT_ADAPTER=$LAYOUT_ADAPTER LAYOUT_MODEL_NAME=$LAYOUT_MODEL_NAME BOOKSMITH_COMMIT=$COMMIT \
    BOOKSMITH_SCHEMA=/app/schema PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "layout"]
