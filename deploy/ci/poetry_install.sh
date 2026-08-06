#!/bin/sh
# Установка зависимостей с fallback-зеркалами PyPI (см. pip_mirror_env.sh).
#
# Poetry не читает PIP_INDEX_URL и ходит на pypi.org. Добавление source через
# `poetry source add` ломает синхрон с poetry.lock — поэтому при зеркале
# ставим pinned-зависимости из lock через pip (он уважает PIP_INDEX_URL).
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck source=./pip_mirror_env.sh
. "$SCRIPT_DIR/pip_mirror_env.sh"

_lock_to_requirements() {
    python - <<'PY'
import tomllib
from pathlib import Path

lock = tomllib.loads(Path("poetry.lock").read_text(encoding="utf-8"))
lines = []
for pkg in lock.get("package", []):
    groups = pkg.get("groups") or []
    if "main" not in groups:
        continue
    lines.append(f'{pkg["name"]}=={pkg["version"]}')
Path("/tmp/requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Exported {len(lines)} packages from poetry.lock → /tmp/requirements.txt")
PY
}

_pyproject_to_requirements() {
    python - <<'PY'
import tomllib
from pathlib import Path

deps = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
Path("/tmp/requirements.txt").write_text("\n".join(deps) + "\n", encoding="utf-8")
PY
}

if [ -n "${PIP_INDEX_URL:-}" ]; then
    echo "Mirror mode (PIP_INDEX_URL=$PIP_INDEX_URL) — install via pip, not poetry."
    if [ -f poetry.lock ]; then
        _lock_to_requirements
    else
        echo "poetry.lock отсутствует — берём зависимости из pyproject.toml."
        _pyproject_to_requirements
    fi
    pip install --no-cache-dir -r /tmp/requirements.txt
    exit 0
fi

# PyPI доступен — обычный путь через Poetry.
if ! command -v poetry >/dev/null 2>&1; then
    pip install --no-cache-dir poetry
fi

if [ -f poetry.lock ]; then
    poetry install --no-interaction --no-ansi --no-root "$@"
else
    echo "poetry.lock отсутствует — ставим зависимости напрямую через pip из pyproject.toml."
    _pyproject_to_requirements
    pip install --no-cache-dir -r /tmp/requirements.txt
fi
