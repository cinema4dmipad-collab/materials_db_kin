"""Export main-group pins from poetry.lock to a requirements.txt path (argv[1])."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: export_lock_requirements.py <out.txt>', file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    lock = tomllib.loads(Path('poetry.lock').read_text(encoding='utf-8'))
    lines: list[str] = []
    for pkg in lock.get('package', []):
        groups = pkg.get('groups') or []
        if 'main' not in groups:
            continue
        lines.append(f'{pkg["name"]}=={pkg["version"]}')
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Exported {len(lines)} packages from poetry.lock -> {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
