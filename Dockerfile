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

# Build-args → ENV, чтобы pip_mirror_env.sh / poetry_install.sh видели зеркало.
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_MIRROR_URLS=${PIP_MIRROR_URLS} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

# pg_dump major must be >= Postgres server major (prod may be 18.x).
ARG POSTGRES_CLIENT_MAJOR=18
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg libpq5 libpq-dev gcc \
        libreoffice-writer-nogui fonts-dejavu-core \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-${POSTGRES_CLIENT_MAJOR} \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/ci/pip_mirror_env.sh deploy/ci/poetry_install.sh /tmp/
RUN chmod +x /tmp/pip_mirror_env.sh /tmp/poetry_install.sh

RUN . /tmp/pip_mirror_env.sh \
    && pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* ./
# poetry_install.sh подхватывает PIP_* и при недоступном pypi.org берёт зеркало.
RUN sh /tmp/poetry_install.sh \
    && rm -rf "$POETRY_CACHE_DIR"

COPY . .
RUN sh /tmp/poetry_install.sh \
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

RUN mkdir -p /backups /backups/tmp \
    && chown -R appuser:appuser /backups

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
