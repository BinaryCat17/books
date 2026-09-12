FROM python:3.12-slim
ARG COMMIT=""
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
WORKDIR /app
COPY schema /app/schema
COPY images/metrics/pyproject.toml images/metrics/constraints.txt /app/
COPY images/metrics/metrics /app/metrics
RUN uv pip install --system --no-cache -c constraints.txt .
ENV BOOKSMITH_HOME=/data BOOKSMITH_SCHEMA=/app/schema PYTHONUNBUFFERED=1 BOOKSMITH_COMMIT=$COMMIT
EXPOSE 8000
CMD ["python", "-m", "metrics"]
