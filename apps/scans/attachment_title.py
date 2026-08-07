from apps.core.sequenced_title import default_sequenced_title


def default_scan_attachment_title(scan) -> str:
    titles = scan.attachments.values_list('title', flat=True)
    base = (scan.title or 'Скан').strip() or 'Скан'
    return default_sequenced_title(base, titles, scan.attachments.count())
