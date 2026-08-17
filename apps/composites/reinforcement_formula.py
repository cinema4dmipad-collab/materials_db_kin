"""Compact stacking-sequence notation from ply angles.

Examples from the sample-density table:
``(0/0)8``, ``(0/90)4/(90/0)4``, ``((0/90)/(+45/-45))2/((-45/+45)/(90/0))2``.
"""

from __future__ import annotations


def _signed_angle(angle) -> float:
    value = ((float(angle) + 180.0) % 360.0) - 180.0
    if value > 90.0:
        value -= 180.0
    elif value < -90.0:
        value += 180.0
    return value


def format_ply_angle(angle) -> str:
    value = _signed_angle(angle)
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 1e-9:
        ival = int(round(rounded))
        if ival == 0:
            return '0'
        if ival == 90:
            return '90'
        if ival == -90:
            return '-90'
        if ival > 0:
            return f'+{ival}'
        return str(ival)
    if rounded > 0:
        text = str(rounded).replace(',', '.')
        return f'+{text}'
    return str(rounded).replace(',', '.')


def _pair_tokens(angles: list) -> list[str]:
    tokens = []
    count = len(angles)
    index = 0
    while index + 1 < count:
        left = format_ply_angle(angles[index])
        right = format_ply_angle(angles[index + 1])
        tokens.append(f'({left}/{right})')
        index += 2
    if index < count:
        tokens.append(f'({format_ply_angle(angles[index])})')
    return tokens


def _format_repeat(block: list[str], repeats: int) -> str:
    if len(block) == 1:
        return f'{block[0]}{repeats}'
    inner = _encode_tokens(block)
    return f'({inner}){repeats}'


def _longest_repeating_prefix(tokens: list[str]) -> tuple[int, str]:
    length = len(tokens)
    for prefix_len in range(length, 1, -1):
        prefix = tokens[:prefix_len]
        for period in range(1, prefix_len // 2 + 1):
            if prefix_len % period != 0:
                continue
            repeats = prefix_len // period
            if repeats < 2:
                continue
            block = prefix[:period]
            if block * repeats == prefix:
                return prefix_len, _format_repeat(block, repeats)
    return 1, tokens[0]


def _encode_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ''
    parts = []
    index = 0
    while index < len(tokens):
        consumed, encoded = _longest_repeating_prefix(tokens[index:])
        parts.append(encoded)
        index += consumed
    return '/'.join(parts)


def build_reinforcement_formula(angles) -> str:
    """Return laminate notation for a sequence of ply angles (full stack)."""
    values = list(angles)
    if not values:
        return ''
    return _encode_tokens(_pair_tokens(values))
