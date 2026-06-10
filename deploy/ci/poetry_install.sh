#!/bin/sh
# Установка зависимостей с fallback-зеркалами PyPI (см. pip_mirror_env.sh).
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck source=./pip_mirror_env.sh
. "$SCRIPT_DIR/pip_mirror_env.sh"

if [ -f poetry.lock ]; then
    if ! command -v poetry >/dev/null 2>&1; then
        pip install --no-cache-dir poetry
    fi
    poetry install --no-interaction --no-ansi --no-root "$@"
else
    echo "poetry.lock отсутствует — ставим зависимости напрямую через pip из pyproject.toml."
    python -c "import tomllib; from pathlib import Path; deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']; print('\n'.join(deps))" > /tmp/requirements.txt
    pip install --no-cache-dir -r /tmp/requirements.txt
fi
