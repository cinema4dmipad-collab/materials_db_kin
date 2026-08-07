"""Shared attachment preview: kinds, LibreOffice convert, post-save processing."""

from apps.core.attachments.kinds import detect_attachment_kind
from apps.core.attachments.processing import process_attachment_preview

__all__ = [
    'detect_attachment_kind',
    'process_attachment_preview',
]
