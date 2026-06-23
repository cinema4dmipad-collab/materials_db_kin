#!/bin/sh
# Полный деплой по SSH на сервере Dokploy (каталог code после git clone).
# НЕ подставлять в Dokploy UI → Command (там выполняется "docker <Command>").
# В UI поле Command оставьте пустым — см. deploy/DOKPLOY.md
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

sh deploy/write-build-commit.sh

if [ -f .build-commit ]; then
  export GIT_COMMIT="$(cat .build-commit)"
  export CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA:-$GIT_COMMIT}"
fi

if [ -f .env ] && [ -z "${COMPOSE_PROJECT_NAME:-}" ]; then
  # Dokploy пишет APP_NAME / COMPOSE_PROJECT_NAME в .env рядом с compose.
  COMPOSE_PROJECT_NAME="$(grep -E '^COMPOSE_PROJECT_NAME=' .env | tail -1 | cut -d= -f2- | tr -d '\r\"' || true)"
  export COMPOSE_PROJECT_NAME
fi

project="${COMPOSE_PROJECT_NAME:-${APP_NAME:-materials-db}}"
exec docker compose -p "$project" -f docker-compose.prod.yml up -d --build --remove-orphans "$@"
