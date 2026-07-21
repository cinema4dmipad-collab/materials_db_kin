from __future__ import annotations

import re

REQUIRED_COLUMNS = frozenset({'code'})

OPTIONAL_COLUMNS = frozenset({
    'name',
    'description',
    'struct_type',
    'tags',
    'property_name',
    'value_kind',
    'value',
    'value_b',
    'notes',
    'home_workspace',
})

KNOWN_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

COLUMN_ALIASES: dict[str, str] = {
    'material_code': 'code',
    'material_name': 'name',
    'structure_type': 'struct_type',
    'structure_type_code': 'struct_type',
    'property': 'property_name',
    'tag': 'tags',
    'value_kind': 'value_kind',
    'value_min': 'value',
    'value_max': 'value_b',
    'tolerance': 'value_b',
}


def normalize_header(raw: str) -> str:
    text = (raw or '').strip().lower()
    text = re.sub(r'[\s\-]+', '_', text)
    text = re.sub(r'[^\w]', '', text)
    return COLUMN_ALIASES.get(text, text)


def normalize_row(raw_row: dict, *, row_number: int) -> dict:
    normalized: dict[str, str] = {}
    for key, value in raw_row.items():
        column = normalize_header(str(key))
        if column not in KNOWN_COLUMNS:
            continue
        if value is None:
            text = ''
        elif isinstance(value, str):
            text = value.strip()
        else:
            text = str(value).strip()
        normalized[column] = text
    normalized['_row_number'] = row_number
    return normalized


def is_blank_row(row: dict) -> bool:
    return not any(
        (row.get(column) or '').strip()
        for column in KNOWN_COLUMNS
        if column in row
    )
