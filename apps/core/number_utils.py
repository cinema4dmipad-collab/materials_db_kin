from decimal import Decimal, InvalidOperation


def normalize_decimal_input(value) -> str:
    """Преобразует ввод пользователя (запятая) в формат с точкой для парсинга."""
    if value is None:
        return ''
    text = str(value).strip().replace('\u00a0', ' ').replace(' ', '')
    if not text:
        return ''
    return text.replace(',', '.')


def parse_decimal(value):
    if value in (None, ''):
        return None
    if isinstance(value, Decimal):
        return value
    normalized = normalize_decimal_input(value)
    if not normalized:
        return None
    return Decimal(normalized)


def parse_float(value):
    if value in (None, ''):
        return None
    if isinstance(value, float):
        return value
    normalized = normalize_decimal_input(value)
    if not normalized:
        return None
    return float(normalized)


def canonical_number_string(value) -> str:
    """Нормализует числовую строку для хранения (с точкой)."""
    normalized = normalize_decimal_input(value)
    if not normalized:
        return ''
    decimal_value = Decimal(normalized)
    return format(decimal_value, 'f').rstrip('0').rstrip('.') or '0'


def format_decimal_display(value, decimal_places: int | None = None) -> str:
    if value is None or value == '':
        return ''
    try:
        decimal_value = parse_decimal(value)
        if decimal_value is None:
            return str(value).replace('.', ',')
        if decimal_places is not None:
            if decimal_places == 0:
                exp = Decimal('1')
            else:
                exp = Decimal(f'1.{"0" * decimal_places}')
            decimal_value = decimal_value.quantize(exp)
        text = format(decimal_value, 'f')
    except (InvalidOperation, ValueError, TypeError):
        return str(value).replace('.', ',')
    return text.replace('.', ',')
