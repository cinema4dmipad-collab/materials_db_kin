#!/bin/sh
# Write .build-commit in project root before docker compose build (Dokploy host).
set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

commit="$(sh deploy/ci/resolve_git_commit.sh "$ROOT")"
if [ -z "$commit" ]; then
  echo "WARN: could not resolve git commit hash for BUILD_COMMIT" >&2
  rm -f .build-commit
  exit 0
fi

printf '%s' "$commit" > .build-commit
echo "BUILD_COMMIT source: $commit (.build-commit)"
