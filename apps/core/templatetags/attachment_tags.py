from django import template

from apps.core.attachments.kinds import KIND_EXCEL, KIND_PDF, KIND_WORD, KIND_LABELS
from apps.core.attachments.model_api import attachment_has_preview, attachment_kind
from apps.core.attachments.statuses import (
    PREVIEW_FAILED,
    PREVIEW_PENDING,
    PREVIEW_READY,
    PREVIEW_SKIPPED,
)

register = template.Library()


@register.inclusion_tag('includes/attachment_preview_cell.html')
def attachment_preview_cell(attachment, preview_url=''):
    """Render preview icon / PDF link for an attachment row."""
    kind = attachment_kind(attachment)
    status = getattr(attachment, 'preview_status', 'none')
    href = preview_url if preview_url and attachment_has_preview(attachment) else ''
    return {
        'attachment': attachment,
        'kind': kind,
        'kind_label': KIND_LABELS.get(kind, 'Файл'),
        'status': status,
        'preview_url': href,
        'is_excel': kind == KIND_EXCEL,
        'is_word': kind == KIND_WORD,
        'is_pdf': kind == KIND_PDF,
        'is_ready': status == PREVIEW_READY,
        'is_pending': status == PREVIEW_PENDING,
        'is_failed': status == PREVIEW_FAILED,
        'is_skipped': status == PREVIEW_SKIPPED,
    }
