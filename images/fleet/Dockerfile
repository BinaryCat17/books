FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends docker.io ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY images/fleet/pyproject.toml /app/
COPY images/fleet/fleet /app/fleet
RUN uv pip install --system --no-cache .
ENV BOOKSMITH_HOME=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "fleet"]
