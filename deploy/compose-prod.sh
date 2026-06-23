#!/bin/sh
# Обёртка для Dokploy / ручного деплоя: подставляет hash коммита в build args compose.
# Пример команды сборки в Dokploy:
#   sh deploy/compose-prod.sh up -d --build
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -z "${GIT_COMMIT:-}" ] && command -v git >/dev/null 2>&1; then
  GIT_COMMIT="$(git rev-parse --short=7 HEAD 2>/dev/null || true)"
fi
export GIT_COMMIT
export CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA:-${GIT_COMMIT:-}}"

exec docker compose -f docker-compose.prod.yml "$@"
