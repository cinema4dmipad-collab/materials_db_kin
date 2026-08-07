import re

_UNIT_MARKER_RE = re.compile(r'[\d/%°²³·\-]')
_SHORT_UNIT_RE = re.compile(r'^[A-Za-zА-Яа-яμ%/°²³·\-]{1,8}$')


def looks_like_unit(value: str) -> bool:
    value = (value or '').strip()
    if not value or len(value) > 50 or ' ' in value:
        return False
    if _UNIT_MARKER_RE.search(value):
        return True
    return bool(_SHORT_UNIT_RE.match(value))


def split_label_and_unit(label: str) -> tuple[str, str]:
    label = (label or '').strip()
    if ', ' not in label:
        return label, ''
    base, candidate = label.rsplit(', ', 1)
    candidate = candidate.strip()
    if looks_like_unit(candidate):
        return base.strip() or label, candidate
    return label, ''
