from functools import lru_cache
from pathlib import Path
import os
import subprocess

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / 'pyproject.toml'
DEFAULT_VERSION = '0.0.0'
DEFAULT_COMMIT_LENGTH = 7


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Application version from pyproject.toml ([project].version)."""
    if not PYPROJECT_PATH.is_file():
        return DEFAULT_VERSION
    with PYPROJECT_PATH.open('rb') as pyproject_file:
        data = tomllib.load(pyproject_file)
    version = (data.get('project') or {}).get('version')
    if not version:
        return DEFAULT_VERSION
    return str(version).strip()


@lru_cache(maxsize=1)
def get_git_commit_hash(*, length: int = DEFAULT_COMMIT_LENGTH) -> str:
    """Short git commit hash from env (CI/Docker) or local repository."""
    for env_name in ('GIT_COMMIT', 'CI_COMMIT_SHORT_SHA', 'CI_COMMIT_SHA'):
        value = os.environ.get(env_name, '').strip()
        if not value:
            continue
        if env_name == 'CI_COMMIT_SHA' and len(value) > length:
            return value[:length]
        return value

    try:
        result = subprocess.run(
            ['git', '-C', str(PROJECT_ROOT), 'rev-parse', f'--short={length}', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ''

    if result.returncode != 0:
        return ''
    return result.stdout.strip()


def format_version_with_commit(version: str | None = None, commit: str | None = None) -> str:
    version_value = (version or get_app_version()).strip() or DEFAULT_VERSION
    commit_value = (commit if commit is not None else get_git_commit_hash()).strip()
    if not commit_value:
        return version_value
    return f'{version_value} · {commit_value}'
