from __future__ import annotations

IMPORT_SOURCE_NOTE_PREFIX = 'Создано из файла импорта:'


def with_import_source_note(description: str | None, filename: str | None) -> str:
    """Добавляет в описание пометку об источнике импорта (без дублирования)."""
    name = (filename or '').strip()
    text = (description or '').strip()
    if not name:
        return text
    note = f'{IMPORT_SOURCE_NOTE_PREFIX} {name}'
    if note in text.splitlines():
        return text
    if any(line.startswith(IMPORT_SOURCE_NOTE_PREFIX) for line in text.splitlines()):
        # Уже есть другая пометка — не дублируем.
        return text
    if text:
        return f'{text}\n\n{note}'
    return note


def parse_import_source_filename(description: str | None) -> str:
    for line in (description or '').splitlines():
        stripped = line.strip()
        if stripped.startswith(IMPORT_SOURCE_NOTE_PREFIX):
            return stripped[len(IMPORT_SOURCE_NOTE_PREFIX) :].strip()
    return ''


def strip_import_source_note(description: str | None) -> str:
    lines = [
        line
        for line in (description or '').splitlines()
        if not line.strip().startswith(IMPORT_SOURCE_NOTE_PREFIX)
    ]
    return '\n'.join(lines).strip()
