"""Render the first page of a PDF to a PNG thumbnail."""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium

# Target width in pixels for list thumbnails (Google Drive–style).
DEFAULT_TARGET_WIDTH = 400


class PdfThumbnailError(RuntimeError):
    pass


def render_pdf_first_page_to_png(
    pdf_source: Path | bytes | bytearray,
    *,
    target_width: int = DEFAULT_TARGET_WIDTH,
) -> bytes:
    """
    Rasterize page 0 of ``pdf_source`` to PNG bytes.

    Scales so the page width is about ``target_width`` pixels.
    """
    if isinstance(pdf_source, (bytes, bytearray)):
        data = bytes(pdf_source)
        if not data:
            raise PdfThumbnailError('Пустой PDF.')
        pdf = pdfium.PdfDocument(data)
    else:
        path = Path(pdf_source)
        if not path.is_file():
            raise PdfThumbnailError(f'PDF не найден: {path}')
        pdf = pdfium.PdfDocument(str(path))

    try:
        if len(pdf) < 1:
            raise PdfThumbnailError('В PDF нет страниц.')
        page = pdf[0]
        try:
            width = max(page.get_width(), 1.0)
            scale = max(target_width / width, 0.1)
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG', optimize=True)
            return buffer.getvalue()
        finally:
            page.close()
    finally:
        pdf.close()
