FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/
WORKDIR /app
COPY schema /app/schema
COPY images/backend/pyproject.toml /app/
COPY images/backend/backend /app/backend
RUN uv pip install --system --no-cache .
ENV BOOKSMITH_HOME=/data BOOKSMITH_SCHEMA=/app/schema PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "backend"]
