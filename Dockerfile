ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
ARG PIP_MIRROR_URLS=
ARG GIT_COMMIT=
ARG CI_COMMIT_SHORT_SHA=
ARG DOKPLOY_COMMIT_HASH=
ARG SOURCE_COMMIT=
# Bump in Dokploy env (BUILD_CACHE_BUST=2) to force rebuild after Dockerfile changes.
ARG BUILD_CACHE_BUST=1

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

RUN . /tmp/pip_mirror_env.sh \
    && pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-ansi --no-root \
    && rm -rf "$POETRY_CACHE_DIR"

COPY . .
RUN poetry install --no-ansi --no-root \
    && rm -rf "$POETRY_CACHE_DIR"

ARG GIT_COMMIT=
ARG CI_COMMIT_SHORT_SHA=
ARG DOKPLOY_COMMIT_HASH=
ARG SOURCE_COMMIT=
ARG BUILD_CACHE_BUST=1
RUN chmod +x /app/deploy/ci/finalize_app_image.sh \
    && BUILD_CACHE_BUST="${BUILD_CACHE_BUST}" \
       GIT_COMMIT="${GIT_COMMIT}" \
       CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA}" \
       DOKPLOY_COMMIT_HASH="${DOKPLOY_COMMIT_HASH}" \
       SOURCE_COMMIT="${SOURCE_COMMIT}" \
       sh /app/deploy/ci/finalize_app_image.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
