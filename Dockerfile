FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-ansi --no-root \
    && rm -rf "$POETRY_CACHE_DIR"

COPY . .
RUN poetry install --no-ansi --no-root \
    && rm -rf "$POETRY_CACHE_DIR"

RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app \
    && chmod +x /app/deploy/entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
