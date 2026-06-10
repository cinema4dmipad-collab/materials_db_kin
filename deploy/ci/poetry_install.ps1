# Установка зависимостей Poetry для Windows shell runner GitLab CI.
$ErrorActionPreference = 'Stop'

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:POETRY_NO_INTERACTION = '1'

if ($env:PIP_INDEX_URL) {
    Write-Host "Using PIP_INDEX_URL: $env:PIP_INDEX_URL"
}

if (Test-Path 'poetry.lock') {
    if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
        python -m pip install --no-cache-dir poetry
    }
    poetry install --no-interaction --no-ansi --no-root @args
} else {
    Write-Host 'poetry.lock missing — installing dependencies from pyproject.toml via pip.'
    python -c @"
import tomllib
from pathlib import Path

deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']
print('\n'.join(deps))
"@ | Set-Content -Encoding utf8 requirements-ci.txt
    python -m pip install --no-cache-dir -r requirements-ci.txt
}
