#!/bin/sh
# Print a short git commit hash (7 chars) or nothing.
# Used on the host before docker compose build and inside Dockerfile.
set -eu

root="${1:-.}"
cd "$root" || exit 0

sanitize() {
  value="$(printf '%s' "$1" | tr -d '[:space:]')"
  case "$value" in
    ''|*'$'*|*'('* )
      return 1
      ;;
  esac
  case "$value" in
    *[!0-9a-fA-F]*)
      return 1
      ;;
  esac
  if [ "${#value}" -lt 7 ]; then
    return 1
  fi
  printf '%s' "$value" | cut -c1-7 | tr 'A-F' 'a-f'
}

for var in GIT_COMMIT CI_COMMIT_SHORT_SHA DOKPLOY_COMMIT_HASH SOURCE_COMMIT; do
  eval "candidate=\${$var:-}"
  if sanitized="$(sanitize "$candidate" 2>/dev/null)"; then
    printf '%s' "$sanitized"
    exit 0
  fi
done

if [ -f .build-commit ]; then
  if sanitized="$(sanitize "$(cat .build-commit")" 2>/dev/null)"; then
    printf '%s' "$sanitized"
    exit 0
  fi
done

if command -v git >/dev/null 2>&1 && git rev-parse --short=7 HEAD >/dev/null 2>&1; then
  git rev-parse --short=7 HEAD | tr 'A-F' 'a-f'
  exit 0
fi

if [ ! -f .git/HEAD ]; then
  exit 0
fi

read -r head_line < .git/HEAD || exit 0
case "$head_line" in
  ref:*)
    ref="$(printf '%s' "$head_line" | sed 's/^ref: //' | tr -d '[:space:]')"
    if [ -f ".git/$ref" ]; then
      read -r full_hash < ".git/$ref" || exit 0
      full_hash="$(printf '%s' "$full_hash" | tr -d '[:space:]')"
      if sanitized="$(sanitize "$full_hash" 2>/dev/null)"; then
        printf '%s' "$sanitized"
        exit 0
      fi
    fi
    if [ -f .git/packed-refs ]; then
      full_hash="$(grep " $ref\$" .git/packed-refs 2>/dev/null | awk 'NR==1 {print $1}')"
      full_hash="$(printf '%s' "$full_hash" | tr -d '[:space:]')"
      if sanitized="$(sanitize "$full_hash" 2>/dev/null)"; then
        printf '%s' "$sanitized"
        exit 0
      fi
    fi
    ;;
  *)
    full_hash="$(printf '%s' "$head_line" | tr -d '[:space:]')"
    if sanitized="$(sanitize "$full_hash" 2>/dev/null)"; then
      printf '%s' "$sanitized"
      exit 0
    fi
    ;;
esac

exit 0
