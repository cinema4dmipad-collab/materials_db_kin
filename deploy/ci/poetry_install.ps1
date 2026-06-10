# Установка зависимостей Poetry для Windows shell runner GitLab CI.
$ErrorActionPreference = 'Stop'

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:POETRY_NO_INTERACTION = '1'

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & python -m uv @Args
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed: uv $($Args -join ' ') (exit $LASTEXITCODE)"
    }
}

function Ensure-Uv {
    if (python -m uv --version 2>$null) {
        return
    }

    Write-Host 'Installing uv to provision Python 3.13...'
    python -m pip install --user uv
}

function Get-Python313Executable {
    Ensure-Uv

    $found = $null
    try {
        $found = (& python -m uv python find 3.13 2>$null | Select-Object -Last 1).Trim()
    } catch {
        $found = $null
    }

    if (-not $found -or -not (Test-Path -LiteralPath $found)) {
        Write-Host 'Python 3.13 not found — installing via uv...'
        Invoke-Uv python install 3.13
        $found = (& python -m uv python find 3.13 | Select-Object -Last 1).Trim()
    }

    if ($found -and (Test-Path -LiteralPath $found)) {
        return $found
    }

    foreach ($command in @('py -3.13', 'python3.13')) {
        try {
            $executable = (Invoke-Expression "$command -c `"import sys; print(sys.executable)`"" 2>$null).Trim()
            if (-not $executable) {
                continue
            }
            $version = (Invoke-Expression "$command -c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`"" 2>$null).Trim()
            if ($version -ge '3.13' -and (Test-Path -LiteralPath $executable)) {
                return $executable
            }
        } catch {
            continue
        }
    }

    throw 'Python 3.13 is required but could not be installed or found on the runner.'
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
