import re
from collections.abc import Iterable

_SEQUENCE_SUFFIX_RE = re.compile(r'#(\d{4})\s*$')


def format_sequence_suffix(number: int) -> str:
    return f'#{number:04d}'


def next_sequence_number(existing_titles: Iterable[str], existing_count: int) -> int:
    max_number = 0
    for title in existing_titles:
        match = _SEQUENCE_SUFFIX_RE.search(title or '')
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max(max_number, existing_count) + 1


def default_sequenced_title(base_name: str, existing_titles: Iterable[str], existing_count: int) -> str:
    number = next_sequence_number(existing_titles, existing_count)
    return f'{base_name} {format_sequence_suffix(number)}'
