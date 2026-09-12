FROM python:3.12-slim
ARG COMMIT=""
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY schema /app/schema
COPY images/datasets/pyproject.toml images/datasets/constraints.txt /app/
COPY images/datasets/datasets /app/datasets
RUN uv pip install --system --no-cache -c constraints.txt .
ENV BOOKSMITH_HOME=/data BOOKSMITH_SCHEMA=/app/schema PYTHONUNBUFFERED=1 BOOKSMITH_COMMIT=$COMMIT
ENTRYPOINT ["python", "-m", "datasets"]
