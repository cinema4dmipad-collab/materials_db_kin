ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
ARG PIP_MIRROR_URLS=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/ci/pip_mirror_env.sh /tmp/pip_mirror_env.sh
RUN chmod +x /tmp/pip_mirror_env.sh

COPY pyproject.toml poetry.lock* ./
RUN . /tmp/pip_mirror_env.sh \
    && python -c "import tomllib; from pathlib import Path; deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']; print('\n'.join(deps))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -rf "$POETRY_CACHE_DIR"

COPY . .

RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app \
    && chmod +x /app/deploy/entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
