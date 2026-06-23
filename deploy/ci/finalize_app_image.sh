#!/bin/sh
# Final image setup: record BUILD_COMMIT and create appuser.
set -eu

echo "BUILD_CACHE_BUST=${BUILD_CACHE_BUST:-1}"

chmod +x /app/deploy/ci/resolve_git_commit.sh
RESOLVED="$(
  GIT_COMMIT="${GIT_COMMIT:-}" \
  CI_COMMIT_SHORT_SHA="${CI_COMMIT_SHORT_SHA:-}" \
  DOKPLOY_COMMIT_HASH="${DOKPLOY_COMMIT_HASH:-}" \
  SOURCE_COMMIT="${SOURCE_COMMIT:-}" \
  sh /app/deploy/ci/resolve_git_commit.sh /app
)" || RESOLVED=""

if [ -n "$RESOLVED" ]; then
  printf '%s' "$RESOLVED" > /app/BUILD_COMMIT
  echo "Recorded BUILD_COMMIT=$RESOLVED"
else
  echo "WARN: BUILD_COMMIT not resolved during image build" >&2
  if [ -f /app/.git/HEAD ]; then
    echo "Found .git/HEAD but could not parse commit" >&2
    cat /app/.git/HEAD >&2 || true
  else
    echo "No .git/HEAD in build context" >&2
  fi
fi

if ! id appuser >/dev/null 2>&1; then
  adduser --disabled-password --gecos '' appuser
fi
mkdir -p /app/staticfiles /app/media
chown -R appuser:appuser /app
chmod +x /app/deploy/entrypoint.sh
