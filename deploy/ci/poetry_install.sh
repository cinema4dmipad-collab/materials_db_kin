#!/bin/sh
# Установка зависимостей с fallback-зеркалами PyPI (см. pip_mirror_env.sh).
# Poetry по умолчанию ходит на pypi.org — при выбранном зеркале добавляем его как primary source.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck source=./pip_mirror_env.sh
. "$SCRIPT_DIR/pip_mirror_env.sh"

if ! command -v poetry >/dev/null 2>&1; then
    pip install --no-cache-dir poetry
fi

# Poetry не читает PIP_INDEX_URL сам — подключаем зеркало как primary.
if [ -n "${PIP_INDEX_URL:-}" ]; then
    echo "Poetry primary source → $PIP_INDEX_URL"
    # Идемпотентно: повторный add в том же слое Docker не критичен.
    poetry source remove corp >/dev/null 2>&1 || true
    poetry source add --priority=primary corp "$PIP_INDEX_URL"
fi

if [ -f poetry.lock ]; then
    poetry install --no-interaction --no-ansi --no-root "$@"
else
    echo "poetry.lock отсутствует — ставим зависимости напрямую через pip из pyproject.toml."
    python -c "import tomllib; from pathlib import Path; deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']; print('\n'.join(deps))" > /tmp/requirements.txt
    pip install --no-cache-dir -r /tmp/requirements.txt
fi
