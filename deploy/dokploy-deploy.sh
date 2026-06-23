#!/bin/sh
# Custom deploy command for Dokploy Compose service.
# Settings → Compose → Advanced → Command (или аналог):
#   sh deploy/dokploy-deploy.sh
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

sh deploy/write-build-commit.sh

if [ -f .build-commit ]; then
  export GIT_COMMIT="$(cat .build-commit)"
  export CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA:-$GIT_COMMIT}"
fi

exec docker compose -f docker-compose.prod.yml up -d --build --remove-orphans "$@"
