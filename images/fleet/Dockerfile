FROM python:3.12-slim
ARG DOCKER_VERSION=29.1.3
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends curl ca-certificates \
 && curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY images/fleet/pyproject.toml images/fleet/constraints.txt /app/
COPY images/fleet/fleet /app/fleet
RUN uv pip install --system --no-cache -c constraints.txt .
ENV BOOKSMITH_HOME=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "fleet"]
