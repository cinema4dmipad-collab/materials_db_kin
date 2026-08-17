from django import template

from apps.scans.keenetix_links import keenetix_scan_url_for
from apps.scans.previews import (
    DEFAULT_PREVIEW_KIND,
    PREVIEW_KINDS,
    preview_file,
    web_preview_url,
)

register = template.Library()


@register.simple_tag
def scan_preview_slides(scan):
    """Slides for B-XZ / B-YZ / C-scan carousel (C is preferred initial)."""
    rows = []
    first_with_image = None
    preferred_index = 0
    for index, kind in enumerate(PREVIEW_KINDS):
        field = preview_file(scan, kind)
        if field and first_with_image is None:
            first_with_image = index
        if kind.key == DEFAULT_PREVIEW_KIND.key:
            preferred_index = index
        rows.append(
            {
                'kind': kind.slug,
                'label': kind.label,
                'url': web_preview_url(scan, kind) if field else '',
            }
        )
    initial = preferred_index
    preferred_row = rows[preferred_index]
    if not preferred_row['url'] and first_with_image is not None:
        initial = first_with_image
    for index, row in enumerate(rows):
        row['is_initial'] = index == initial
    return rows


@register.filter(name='keenetix_url')
def keenetix_url(scan) -> str:
    """Href for «Открыть в KeenetiX» (custom protocol)."""
    try:
        return keenetix_scan_url_for(scan)
    except (TypeError, ValueError):
        return ''