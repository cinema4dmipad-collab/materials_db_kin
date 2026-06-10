# Установка зависимостей Poetry для Windows shell runner GitLab CI.
$ErrorActionPreference = 'Stop'

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:POETRY_NO_INTERACTION = '1'

function Get-Python313Executable {
    foreach ($command in @('py -3.13', 'python3.13', 'python')) {
        try {
            $executable = Invoke-Expression "$command -c `"import sys; print(sys.executable)`"" 2>$null
            if (-not $executable) {
                continue
            }
            $version = Invoke-Expression "$command -c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`"" 2>$null
            if ($version -ge '3.13') {
                return $executable.Trim()
            }
        } catch {
            continue
        }
    }

    throw 'Python 3.13 is required but was not found (tried py -3.13, python3.13, python).'
}

function Install-FromPyproject {
    Write-Host 'poetry.lock missing — installing dependencies from pyproject.toml via pip.'
    $requirementsPath = Join-Path $PWD 'requirements-ci.txt'
    try {
        python -c @"
import tomllib
from pathlib import Path

deps = tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']
print('\n'.join(deps))
"@ | Set-Content -Encoding utf8 $requirementsPath
    } catch {
        python -m pip install --no-cache-dir tomli
        python -c @"
import tomli
from pathlib import Path

deps = tomli.loads(Path('pyproject.toml').read_text())['project']['dependencies']
print('\n'.join(deps))
"@ | Set-Content -Encoding utf8 $requirementsPath
    }
    python -m pip install --no-cache-dir -r $requirementsPath
}

$pythonExecutable = Get-Python313Executable
Write-Host "Using Python: $pythonExecutable"

if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    & $pythonExecutable -m pip install --no-cache-dir poetry
}

poetry env use $pythonExecutable

if ($env:PIP_INDEX_URL) {
    Write-Host "Using PIP_INDEX_URL: $env:PIP_INDEX_URL"
}

if (Test-Path 'poetry.lock') {
    poetry install --no-interaction --no-ansi --no-root @args
} else {
    Install-FromPyproject
}
