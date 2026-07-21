from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from apps.core.number_utils import normalize_decimal_input
from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
)

PARSE_AUTO = 'auto'
PARSE_TEXT = 'text'
PARSE_NUMBER = 'number'
PARSE_MODES = (
    (PARSE_AUTO, 'Авто (число / диапазон / ± / текст)'),
    (PARSE_TEXT, 'Всегда текст'),
    (PARSE_NUMBER, 'Строго число (иначе сомнение)'),
)
# Короткие подписи для компактного UI маппинга
PARSE_MODES_SHORT = (
    (PARSE_AUTO, 'Авто'),
    (PARSE_TEXT, 'Текст'),
    (PARSE_NUMBER, 'Число'),
)

CONFIDENCE_OK = 'ok'
CONFIDENCE_UNCERTAIN = 'uncertain'

# Типичные «пустые» значения в сводных Excel (прочерк, н/д и т.п.)
_BLANK_CELL_RE = re.compile(
    r'^(?:'
    r'[-–—−]+'  # -, --, —
    r'|n/?a|n\.?\s*a\.?'
    r'|н/?д|н\.?\s*д\.?'
    r'|нет|отсутствует|пусто'
    r'|\.+'
    r')$',
    re.IGNORECASE | re.UNICODE,
)

_TOLERANCE_RE = re.compile(
    r'^\s*([+-]?\d+(?:[.,]\d+)?)\s*[±]\s*([+]?\d+(?:[.,]\d+)?)\s*$',
    re.UNICODE,
)
# В сводных часто пишут «0,27+0,035» / «12+1 /м» вместо «±»
_TOLERANCE_PLUS_RE = re.compile(
    r'^\s*([+-]?\d+(?:[.,]\d+)?)\s*\+\s*([+]?\d+(?:[.,]\d+)?)'
    r'(?:\s*[a-zA-Zа-яА-ЯёЁ%°²³µμ/].*)?$',
    re.UNICODE,
)
_RANGE_RE = re.compile(
    r'^\s*([+-]?\d+(?:[.,]\d+)?)\s*[-–—]\s*([+-]?\d+(?:[.,]\d+)?)\s*$',
    re.UNICODE,
)
_PLAIN_NUMBER_RE = re.compile(r'^\s*[+-]?\d+(?:[.,]\d+)?\s*$')
# число + единицы: «12,5 мм», «4050Н», «0.5%»
_NUMBER_WITH_UNIT_RE = re.compile(
    r'^\s*([+-]?\d+(?:[.,]\d+)?)\s*[a-zA-Zа-яА-ЯёЁ%°²³µμ]+[a-zA-Zа-яА-ЯёЁ0-9%°²³µμ/\-\s]*$',
    re.UNICODE,
)
# «4050/50мм», «4050 / 50 мм» — нагрузка на ширину полоски: берём первое число
_NUMBER_PER_STRIP_RE = re.compile(
    r'^\s*([+-]?\d+(?:[.,]\d+)?)\s*/\s*[+]?\d+(?:[.,]\d+)?\s*[a-zA-Zа-яА-ЯёЁ%°²³µμ]*\s*$',
    re.UNICODE,
)


def is_blank_cell(raw) -> bool:
    """True для None, '' и типовых прочерков/н/д из сводных таблиц."""
    if raw is None:
        return True
    if isinstance(raw, (int, float, Decimal)) and not isinstance(raw, bool):
        return False
    text = str(raw).replace('\u00a0', ' ').strip()
    if not text:
        return True
    return bool(_BLANK_CELL_RE.match(text))


def parse_property_cell(raw, *, mode: str = PARSE_AUTO) -> dict | None:
    """
    Возвращает dict:
      value_kind, value, value_b, confidence, note
    или None если пусто.
    """
    mode = mode or PARSE_AUTO
    if is_blank_cell(raw):
        return None

    if isinstance(raw, (int, float, Decimal)) and not isinstance(raw, bool):
        try:
            text = format(Decimal(str(raw)), 'f').rstrip('0').rstrip('.') or '0'
        except (InvalidOperation, ValueError):
            text = str(raw)
        return _result(VALUE_KIND_SCALAR, text, None, CONFIDENCE_OK, 'число')

    text = str(raw).replace('\u00a0', ' ').strip()
    if not text:
        return None

    if mode == PARSE_TEXT:
        return _result(VALUE_KIND_SCALAR, text, None, CONFIDENCE_OK, 'текст (режим колонки)')

    single_line = ' '.join(text.split())
    multiline = '\n' in str(raw) or len(text) > 80

    match = _TOLERANCE_RE.match(single_line)
    if match:
        return _result(
            VALUE_KIND_TOLERANCE,
            _norm_num(match.group(1)),
            _norm_num(match.group(2)),
            CONFIDENCE_OK,
            '± погрешность',
        )

    match = _TOLERANCE_PLUS_RE.match(single_line)
    if match:
        return _result(
            VALUE_KIND_TOLERANCE,
            _norm_num(match.group(1)),
            _norm_num(match.group(2)),
            CONFIDENCE_OK,
            '± погрешность (из записи с «+»)',
        )

    match = _RANGE_RE.match(single_line)
    if match:
        return _result(
            VALUE_KIND_RANGE,
            _norm_num(match.group(1)),
            _norm_num(match.group(2)),
            CONFIDENCE_OK,
            'диапазон',
        )

    if _PLAIN_NUMBER_RE.match(single_line):
        return _result(
            VALUE_KIND_SCALAR,
            _norm_num(single_line),
            None,
            CONFIDENCE_OK,
            'число',
        )

    # Авто и «строго число»: отделить значение от единиц / «на ширину»
    extracted = _extract_leading_number(single_line)
    if extracted is not None:
        value, note_suffix, confidence = extracted
        if mode == PARSE_NUMBER and confidence == CONFIDENCE_OK:
            confidence = CONFIDENCE_UNCERTAIN
            note_suffix = f'число извлечено из «{single_line[:40]}», проверьте'
        return _result(
            VALUE_KIND_SCALAR,
            value,
            None,
            confidence,
            note_suffix,
        )

    if mode == PARSE_NUMBER:
        return _result(
            VALUE_KIND_SCALAR,
            text,
            None,
            CONFIDENCE_UNCERTAIN,
            'ожидалось число — оставлено текстом, проверьте',
        )

    confidence = CONFIDENCE_UNCERTAIN if multiline or _looks_messy(single_line) else CONFIDENCE_OK
    note = 'сложное значение — проверьте' if confidence == CONFIDENCE_UNCERTAIN else 'текст'
    return _result(VALUE_KIND_SCALAR, text, None, confidence, note)


def _extract_leading_number(single_line: str) -> tuple[str, str, str] | None:
    """
    Вытаскивает ведущее число из «4050 Н», «12,5мм», «4050/ 50мм».
    Возвращает (value, note, confidence) или None.
    """
    strip_match = _NUMBER_PER_STRIP_RE.match(single_line)
    if strip_match:
        return (
            _norm_num(strip_match.group(1)),
            f'число извлечено из «{single_line[:40]}» (единицы/ширина отброшены)',
            CONFIDENCE_OK,
        )

    unit_match = _NUMBER_WITH_UNIT_RE.match(single_line)
    if unit_match:
        return (
            _norm_num(unit_match.group(1)),
            f'число извлечено из «{single_line[:40]}» (единицы отброшены)',
            CONFIDENCE_OK,
        )
    return None


def _looks_messy(text: str) -> bool:
    if '/' in text and any(ch.isdigit() for ch in text):
        return True
    if text.count(' ') > 4 and any(ch.isdigit() for ch in text):
        return True
    if re.search(r'\d', text) and re.search(r'[A-Za-zА-Яа-я]', text):
        return True
    return False


def _result(kind, value, value_b, confidence, note) -> dict:
    return {
        'value_kind': kind,
        'value': value,
        'value_b': value_b,
        'confidence': confidence,
        'note': note,
    }


def _norm_num(raw: str) -> str:
    normalized = normalize_decimal_input(raw)
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return normalized
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'
