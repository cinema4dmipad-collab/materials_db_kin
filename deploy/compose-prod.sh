#!/bin/sh
# Обёртка для ручного деплоя: пишет .build-commit и передаёт hash в build args.
# Пример: sh deploy/compose-prod.sh up -d --build
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

sh deploy/write-build-commit.sh

if [ -f .build-commit ]; then
  export GIT_COMMIT="$(cat .build-commit)"
fi
export CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA:-${GIT_COMMIT:-}}"

exec docker compose -f docker-compose.prod.yml "$@"
