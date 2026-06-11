import re

from apps.structures.sql_executor import SQLExecutor

# Транслитерация кириллицы (ГОСТ-подобная, без внешних зависимостей).
_CYRILLIC = str.maketrans(
    {
        'а': 'a',
        'б': 'b',
        'в': 'v',
        'г': 'g',
        'д': 'd',
        'е': 'e',
        'ё': 'e',
        'ж': 'zh',
        'з': 'z',
        'и': 'i',
        'й': 'y',
        'к': 'k',
        'л': 'l',
        'м': 'm',
        'н': 'n',
        'о': 'o',
        'п': 'p',
        'р': 'r',
        'с': 's',
        'т': 't',
        'у': 'u',
        'ф': 'f',
        'х': 'h',
        'ц': 'ts',
        'ч': 'ch',
        'ш': 'sh',
        'щ': 'sch',
        'ъ': '',
        'ы': 'y',
        'ь': '',
        'э': 'e',
        'ю': 'yu',
        'я': 'ya',
    }
)

SQL_RESERVED_WORDS = frozenset(
    {
        'all',
        'alter',
        'and',
        'any',
        'as',
        'between',
        'by',
        'case',
        'check',
        'column',
        'constraint',
        'create',
        'default',
        'delete',
        'drop',
        'exists',
        'false',
        'foreign',
        'from',
        'group',
        'having',
        'index',
        'insert',
        'into',
        'join',
        'key',
        'left',
        'limit',
        'not',
        'null',
        'offset',
        'on',
        'or',
        'order',
        'primary',
        'references',
        'right',
        'select',
        'set',
        'table',
        'true',
        'union',
        'unique',
        'update',
        'user',
        'using',
        'values',
        'view',
        'where',
    }
)

RESERVED_TABLE_COLUMNS = frozenset({'id', 'created_at', 'updated_at', 'created_by'})

TABLE_PREFIX = 'structures_'


def transliterate(text: str) -> str:
    if not text:
        return ''
    return text.strip().lower().translate(_CYRILLIC)


def normalize_identifier(text: str, *, max_length: int = 50) -> str:
    """Преобразует название в безопасный snake_case для SQL."""
    raw = transliterate(text)
    slug = re.sub(r'[^a-z0-9]+', '_', raw)
    slug = re.sub(r'_+', '_', slug).strip('_')
    if not slug:
        return ''
    if slug[0].isdigit():
        slug = f'f_{slug}'
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('_')
    return slug


def table_name_for_code(code: str) -> str:
    return f'{TABLE_PREFIX}{code}'.replace('-', '_')


def validate_sql_identifier(
    identifier: str,
    *,
    label: str = 'Идентификатор',
    reserved: frozenset[str] | None = None,
) -> str:
    normalized = (identifier or '').strip().lower()
    if not normalized:
        raise ValueError(f'{label} не может быть пустым.')

    SQLExecutor.validate_identifier(normalized)

    if normalized in SQL_RESERVED_WORDS:
        raise ValueError(
            f'{label} «{normalized}» совпадает с зарезервированным SQL-словом. '
            'Выберите другое имя, например добавьте суффикс _value.'
        )

    if reserved and normalized in reserved:
        raise ValueError(
            f'{label} «{normalized}» зарезервировано системой. '
            'Это имя уже используется служебными колонками таблицы.'
        )

    return normalized


def validate_structure_code(code: str) -> str:
    return validate_sql_identifier(code, label='Код типа')


def validate_field_column_name(name: str) -> str:
    return validate_sql_identifier(
        name,
        label='Имя колонки',
        reserved=RESERVED_TABLE_COLUMNS,
    )


def validate_table_name(table_name: str) -> str:
    normalized = validate_sql_identifier(table_name, label='Имя SQL-таблицы')
    if len(normalized) > 100:
        raise ValueError('Имя SQL-таблицы не длиннее 100 символов.')
    if not normalized.startswith(TABLE_PREFIX):
        raise ValueError(
            f'Имя SQL-таблицы должно начинаться с «{TABLE_PREFIX}».'
        )
    suffix = normalized[len(TABLE_PREFIX):]
    if not suffix or not re.fullmatch(r'[a-z][a-z0-9_]*', suffix):
        raise ValueError(
            f'После префикса «{TABLE_PREFIX}» укажите имя в формате snake_case латиницей.'
        )
    return normalized


def resolve_table_name(raw_table_name: str, *, fallback_code: str) -> str:
    manual = (raw_table_name or '').strip()
    if manual:
        return validate_table_name(manual)
    return validate_table_name(table_name_for_code(fallback_code))


def preview_table_name_from_title(title: str) -> str:
    code = normalize_identifier(title, max_length=50)
    if not code:
        return ''
    try:
        return table_name_for_code(validate_structure_code(code))
    except ValueError:
        return table_name_for_code(code)
