from django import template

from apps.scans.keenetix_links import keenetix_scan_url_for

register = template.Library()


@register.filter(name='keenetix_url')
def keenetix_url(scan) -> str:
    """Href for «Открыть в KeenetiX» (custom protocol)."""
    try:
        return keenetix_scan_url_for(scan)
    except (TypeError, ValueError):
        return ''