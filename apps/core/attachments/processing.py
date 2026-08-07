"""Fill preview_pdf / preview_status after an attachment is saved."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from django.core.files import File
from django.db import transaction

from apps.core.attachments.convert import (
    LibreOfficeConvertError,
    LibreOfficeNotFoundError,
    convert_office_to_pdf,
)
from apps.core.attachments.kinds import (
    KIND_EXCEL,
    KIND_OTHER,
    KIND_PDF,
    KIND_WORD,
    detect_attachment_kind,
)
from apps.core.attachments.statuses import (
    PREVIEW_FAILED,
    PREVIEW_NONE,
    PREVIEW_PENDING,
    PREVIEW_READY,
    PREVIEW_SKIPPED,
)

logger = logging.getLogger(__name__)


def schedule_attachment_preview(attachment) -> None:
    """Mark pending kinds and run processing after the DB commit."""
    if not attachment.file:
        return
    kind = detect_attachment_kind(attachment.filename)
    if kind == KIND_EXCEL:
        _set_status(attachment, PREVIEW_SKIPPED)
        return
    if kind == KIND_OTHER:
        _set_status(attachment, PREVIEW_NONE)
        return
    if kind in (KIND_PDF, KIND_WORD):
        _set_status(attachment, PREVIEW_PENDING)
        pk = attachment.pk
        model = type(attachment)

        def _run():
            try:
                obj = model.objects.filter(pk=pk).first()
                if obj is not None:
                    process_attachment_preview(obj)
            except Exception:
                logger.exception('Attachment preview processing failed for %s', pk)

        transaction.on_commit(_run)


def process_attachment_preview(attachment) -> None:
    if not attachment.file:
        _set_status(attachment, PREVIEW_NONE)
        return

    kind = detect_attachment_kind(attachment.filename)
    if kind == KIND_EXCEL:
        _clear_preview_file(attachment)
        _set_status(attachment, PREVIEW_SKIPPED)
        return
    if kind == KIND_OTHER:
        _clear_preview_file(attachment)
        _set_status(attachment, PREVIEW_NONE)
        return

    try:
        if kind == KIND_PDF:
            _store_pdf_as_preview(attachment, use_original=True)
        elif kind == KIND_WORD:
            _convert_word_to_preview(attachment)
        else:
            _set_status(attachment, PREVIEW_NONE)
            return
        _set_status(attachment, PREVIEW_READY)
    except (LibreOfficeNotFoundError, LibreOfficeConvertError, OSError) as exc:
        logger.warning('Preview failed for %s: %s', attachment.pk, exc)
        _clear_preview_file(attachment)
        _set_status(attachment, PREVIEW_FAILED)


def _set_status(attachment, status: str) -> None:
    type(attachment).objects.filter(pk=attachment.pk).update(preview_status=status)
    attachment.preview_status = status


def _clear_preview_file(attachment) -> None:
    if not attachment.preview_pdf:
        return
    name = attachment.preview_pdf.name
    attachment.preview_pdf.delete(save=False)
    type(attachment).objects.filter(pk=attachment.pk).update(preview_pdf='')
    attachment.preview_pdf = None
    if name:
        try:
            attachment.file.storage.delete(name)
        except Exception:
            pass


def _store_pdf_as_preview(attachment, *, use_original: bool) -> None:
    """Copy original PDF bytes into preview_pdf (keeps download/original independent)."""
    storage = attachment.file.storage
    src_name = attachment.file.name
    base = os.path.basename(src_name)
    if not base.lower().endswith('.pdf'):
        base = f'{os.path.splitext(base)[0]}.pdf'

    with storage.open(src_name, 'rb') as src:
        if attachment.preview_pdf:
            attachment.preview_pdf.delete(save=False)
        attachment.preview_pdf.save(base, File(src), save=True)


def _convert_word_to_preview(attachment) -> None:
    storage = attachment.file.storage
    suffix = os.path.splitext(attachment.filename)[1] or '.docx'
    tmp_dir = Path(tempfile.mkdtemp(prefix='lab_attach_'))
    src_path = tmp_dir / f'source{suffix}'
    pdf_path = None
    try:
        with storage.open(attachment.file.name, 'rb') as src, src_path.open('wb') as dest:
            shutil.copyfileobj(src, dest)
        pdf_path = convert_office_to_pdf(src_path)
        with pdf_path.open('rb') as handle:
            if attachment.preview_pdf:
                attachment.preview_pdf.delete(save=False)
            preview_name = f'{os.path.splitext(attachment.filename)[0] or "preview"}.pdf'
            attachment.preview_pdf.save(preview_name, File(handle), save=True)
    finally:
        if pdf_path is not None:
            # convert_office_to_pdf returns file inside a temp out_dir — remove parent
            shutil.rmtree(pdf_path.parent, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
