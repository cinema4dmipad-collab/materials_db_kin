# Установка зависимостей для Windows shell runner GitLab CI.
# Poetry не читает PIP_INDEX_URL — при зеркале ставим pinned deps из poetry.lock через pip
# (как deploy/ci/poetry_install.sh).
$ErrorActionPreference = 'Stop'

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:POETRY_NO_INTERACTION = '1'
if (-not $env:PIP_DEFAULT_TIMEOUT) { $env:PIP_DEFAULT_TIMEOUT = '120' }
if (-not $env:PIP_RETRIES) { $env:PIP_RETRIES = '10' }

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

function Test-PipIndex {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 12 -UseBasicParsing
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Get-HostFromUrl {
    param([Parameter(Mandatory = $true)][string]$Url)
    return ([System.Uri]$Url).Host
}

function Use-PipMirror {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][string]$Url
    )
    $env:PIP_INDEX_URL = $Url
    $env:PIP_TRUSTED_HOST = $HostName
    Write-Host "Используем зеркало: $HostName"
}

function Select-PipMirror {
    if ($env:PIP_INDEX_URL) {
        if (-not $env:PIP_TRUSTED_HOST) {
            $env:PIP_TRUSTED_HOST = Get-HostFromUrl -Url $env:PIP_INDEX_URL
        }
        Write-Host "Используем заданный PIP_INDEX_URL: $($env:PIP_INDEX_URL)"
        return
    }

    if (Test-PipIndex -Url 'https://pypi.org/simple/pip/') {
        Write-Host 'PyPI доступен (pypi.org).'
        return
    }

    Write-Host 'PyPI недоступен — проверяем зеркала...'
    $mirrors = @(
        'https://pypi.tuna.tsinghua.edu.cn/simple/',
        'https://mirrors.aliyun.com/pypi/simple/',
        'https://pypi.mirrors.ustc.edu.cn/simple/',
        'https://repo.huaweicloud.com/repository/pypi/simple/'
    )
    if ($env:PIP_MIRROR_URLS) {
        $mirrors = @($env:PIP_MIRROR_URLS -split '\s+' | Where-Object { $_ })
    }

    foreach ($url in $mirrors) {
        $hostName = Get-HostFromUrl -Url $url
        $probe = ($url.TrimEnd('/') + '/pip/')
        if (Test-PipIndex -Url $probe) {
            Use-PipMirror -HostName $hostName -Url $url
            return
        }
        Write-Host "  недоступно: $hostName"
    }

    Write-Host 'WARNING: ни одно зеркало не ответило на probe — fallback Tsinghua'
    Use-PipMirror -HostName 'pypi.tuna.tsinghua.edu.cn' -Url 'https://pypi.tuna.tsinghua.edu.cn/simple/'
}

function Invoke-PoetryPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & poetry run python @Args
    if ($LASTEXITCODE -ne 0) {
        throw "poetry run python failed (exit $LASTEXITCODE): $($Args -join ' ')"
    }
}

function Export-LockRequirements {
    param([Parameter(Mandatory = $true)][string]$OutPath)
    $code = @'
import tomllib
from pathlib import Path
import sys

lock = tomllib.loads(Path("poetry.lock").read_text(encoding="utf-8"))
lines = []
for pkg in lock.get("package", []):
    groups = pkg.get("groups") or []
    if "main" not in groups:
        continue
    lines.append(f'{pkg["name"]}=={pkg["version"]}')
Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Exported {len(lines)} packages from poetry.lock → {sys.argv[1]}")
'@
    & poetry run python -c $code $OutPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to export poetry.lock → $OutPath"
    }
}

function Install-FromPyproject {
    Write-Host 'poetry.lock missing — installing dependencies from pyproject.toml via pip.'
    $requirementsPath = Join-Path ([System.IO.Path]::GetTempPath()) ("requirements-ci-" + [guid]::NewGuid().ToString() + ".txt")
    $exportCode = @'
import tomllib
from pathlib import Path
import sys
deps = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
Path(sys.argv[1]).write_text("\n".join(deps) + "\n", encoding="utf-8")
'@
    & poetry run python -c $exportCode $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to export pyproject dependencies"
    }
    $pipArgs = @('-m', 'pip', 'install', '--no-cache-dir', '-r', $requirementsPath)
    if ($env:PIP_INDEX_URL) {
        $pipArgs += @('-i', $env:PIP_INDEX_URL)
    }
    if ($env:PIP_TRUSTED_HOST) {
        $pipArgs += @('--trusted-host', $env:PIP_TRUSTED_HOST)
    }
    Invoke-PoetryPython @pipArgs
}

function Install-ViaPipFromLock {
    Write-Host "Mirror mode (PIP_INDEX_URL=$($env:PIP_INDEX_URL)) — install via pip into Poetry env."
    $requirementsPath = Join-Path ([System.IO.Path]::GetTempPath()) ("requirements-ci-lock-" + [guid]::NewGuid().ToString() + ".txt")
    Export-LockRequirements -OutPath $requirementsPath
    $pipArgs = @('-m', 'pip', 'install', '--no-cache-dir', '-r', $requirementsPath)
    if ($env:PIP_INDEX_URL) {
        $pipArgs += @('-i', $env:PIP_INDEX_URL)
    }
    if ($env:PIP_TRUSTED_HOST) {
        $pipArgs += @('--trusted-host', $env:PIP_TRUSTED_HOST)
    }
    Invoke-PoetryPython @pipArgs
}

$pythonExecutable = Get-Python313Executable
Write-Host "Using Python: $pythonExecutable"

if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    & $pythonExecutable -m pip install --no-cache-dir poetry
}

poetry env use $pythonExecutable
Select-PipMirror

if (-not (Test-Path 'poetry.lock')) {
    Install-FromPyproject
    exit 0
}

if ($env:PIP_INDEX_URL) {
    Install-ViaPipFromLock
    exit 0
}

# PyPI доступен — пробуем Poetry; при обрыве сети уходим на зеркало + pip.
Write-Host 'Installing dependencies via Poetry...'
& poetry install --no-interaction --no-ansi --no-root @args
if ($LASTEXITCODE -eq 0) {
    exit 0
}

Write-Host "Poetry install failed (exit $LASTEXITCODE) — fallback to mirror + pip."
$env:PIP_INDEX_URL = $null
$env:PIP_TRUSTED_HOST = $null
# Force mirror selection even if a stale probe thought PyPI was up.
if (Test-PipIndex -Url 'https://pypi.org/simple/pip/') {
    # Still prefer a stable mirror after a flaky Poetry run.
    Use-PipMirror -HostName 'pypi.tuna.tsinghua.edu.cn' -Url 'https://pypi.tuna.tsinghua.edu.cn/simple/'
} else {
    Select-PipMirror
}
if (-not $env:PIP_INDEX_URL) {
    Use-PipMirror -HostName 'pypi.tuna.tsinghua.edu.cn' -Url 'https://pypi.tuna.tsinghua.edu.cn/simple/'
}
Install-ViaPipFromLock
