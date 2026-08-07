"""Helpers used by attachment model instances."""

from __future__ import annotations

from apps.core.attachments.kinds import KIND_LABELS, detect_attachment_kind
from apps.core.attachments.statuses import PREVIEW_READY


def attachment_kind(attachment) -> str:
    return detect_attachment_kind(getattr(attachment, 'filename', '') or '')


def attachment_kind_label(attachment) -> str:
    return KIND_LABELS.get(attachment_kind(attachment), KIND_LABELS['other'])


def attachment_has_preview(attachment) -> bool:
    return bool(
        getattr(attachment, 'preview_status', None) == PREVIEW_READY
        and getattr(attachment, 'preview_pdf', None)
        and attachment.preview_pdf
    )


def delete_attachment_files(attachment) -> None:
    if attachment.file:
        attachment.file.delete(save=False)
    if getattr(attachment, 'preview_pdf', None) and attachment.preview_pdf:
        attachment.preview_pdf.delete(save=False)
