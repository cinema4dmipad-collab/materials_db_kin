#!/usr/bin/env bash
# Same logic as git alias mr-diff, but stdout instead of xclip.
# Run from repo root or any directory inside the repo.

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo 'create MR summary by template:'
echo ''
echo '1. template:'
cat ./.gitlab/merge_request_templates/Default.md 2>/dev/null || true
echo ''
echo '2. diff:'
git diff develop..HEAD -- . ':!poetry.lock'
