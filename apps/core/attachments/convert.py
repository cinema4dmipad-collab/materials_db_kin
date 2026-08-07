"""Convert Office documents to PDF via LibreOffice (soffice)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_SOFFICE_CANDIDATES = (
    os.environ.get('LIBREOFFICE_PATH', ''),
    'soffice',
    'libreoffice',
    r'C:\Program Files\LibreOffice\program\soffice.exe',
    r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    '/usr/bin/soffice',
    '/usr/bin/libreoffice',
)


class LibreOfficeNotFoundError(RuntimeError):
    pass


class LibreOfficeConvertError(RuntimeError):
    pass


def find_soffice() -> str | None:
    for candidate in _SOFFICE_CANDIDATES:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def convert_office_to_pdf(source: Path, *, timeout: int = 120) -> Path:
    """
    Convert ``source`` (Word/ODT/…) to PDF in a temp directory.

    Returns path to the generated PDF. Caller must delete it.
    """
    soffice = find_soffice()
    if not soffice:
        raise LibreOfficeNotFoundError(
            'LibreOffice (soffice) не найден. Установите пакет или задайте LIBREOFFICE_PATH.'
        )
    if not source.is_file():
        raise LibreOfficeConvertError(f'Исходный файл не найден: {source}')

    out_dir = Path(tempfile.mkdtemp(prefix='lab_lo_pdf_'))
    env = os.environ.copy()
    # LibreOffice needs a writable user profile (Docker appuser has no $HOME).
    env.setdefault('HOME', str(out_dir / 'home'))
    (out_dir / 'home').mkdir(parents=True, exist_ok=True)

    cmd = [
        soffice,
        '--headless',
        '--nologo',
        '--nofirststartwizard',
        '--norestore',
        '--convert-to',
        'pdf',
        '--outdir',
        str(out_dir),
        str(source.resolve()),
    ]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise LibreOfficeConvertError('Конвертация в PDF превысила лимит времени.') from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or b'').decode('utf-8', errors='replace')[:500]
        shutil.rmtree(out_dir, ignore_errors=True)
        logger.error('LibreOffice convert failed: %s', stderr)
        raise LibreOfficeConvertError(f'LibreOffice вернул код {completed.returncode}.')

    pdfs = list(out_dir.glob('*.pdf'))
    if not pdfs:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise LibreOfficeConvertError('LibreOffice не создал PDF.')
    return pdfs[0]
