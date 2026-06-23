#!/bin/sh
# Print a short git commit hash (7 chars) or nothing.
# POSIX sh / dash compatible (no nested command substitutions).
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

try_print_sanitized() {
  candidate="$1"
  sanitized="$(sanitize "$candidate" 2>/dev/null || true)"
  if [ -n "$sanitized" ]; then
    printf '%s' "$sanitized"
    exit 0
  fi
}

for var in GIT_COMMIT CI_COMMIT_SHORT_SHA DOKPLOY_COMMIT_HASH SOURCE_COMMIT; do
  eval "candidate=\${$var:-}"
  try_print_sanitized "$candidate"
done

if [ -f .build-commit ]; then
  build_commit_contents="$(cat .build-commit)"
  try_print_sanitized "$build_commit_contents"
fi

if [ -f .git/HEAD ]; then
  read -r head_line < .git/HEAD || head_line=''
  case "$head_line" in
    ref:*)
      ref="$(printf '%s' "$head_line" | sed 's/^ref: //' | tr -d '[:space:]')"
      if [ -f ".git/$ref" ]; then
        read -r full_hash < ".git/$ref" || full_hash=''
        try_print_sanitized "$full_hash"
      fi
      if [ -f .git/packed-refs ]; then
        full_hash="$(grep " $ref\$" .git/packed-refs 2>/dev/null | awk 'NR==1 {print $1}' || true)"
        try_print_sanitized "$full_hash"
      fi
      ;;
    *)
      try_print_sanitized "$head_line"
      ;;
  esac
fi

if command -v git >/dev/null 2>&1 && git rev-parse --short=7 HEAD >/dev/null 2>&1; then
  git rev-parse --short=7 HEAD | tr 'A-F' 'a-f'
  exit 0
fi

exit 0
