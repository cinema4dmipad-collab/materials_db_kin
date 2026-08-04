"""Defaults for scans created via HTTP API (e.g. KeenetiX Lab client)."""

KEENETIX_CLIENT_HEADER = 'X-Client'
KEENETIX_CLIENT_VALUE = 'KeenetiX'
KEENETIX_SOURCE_TAG = 'источник::KeenetiX'

# Hard limits for multipart tag_names (comma-separated).
MAX_SCAN_TAGS_VIA_API = 20
MAX_SCAN_TAG_NAME_LEN = 64


def parse_tag_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for part in str(raw).split(','):
        name = part.strip()
        if not name or len(name) > MAX_SCAN_TAG_NAME_LEN:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= MAX_SCAN_TAGS_VIA_API:
            break
    return names
