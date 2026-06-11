from functools import lru_cache
from pathlib import Path

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / 'pyproject.toml'
DEFAULT_VERSION = '0.0.0'


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
