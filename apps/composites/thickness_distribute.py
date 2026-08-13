"""Distribute target total thickness across unlocked composite layers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


class ThicknessDistributeError(ValueError):
    pass


def distribute_thicknesses(
    thicknesses: list[float | None],
    locked: list[bool],
    target_total: float,
    *,
    decimals: int = 4,
) -> list[float]:
    """
    Split ``target_total`` equally among unlocked layers.

    Locked layers keep their current thickness; their sum is subtracted from
    the target before dividing the remainder.
    """
    if len(thicknesses) != len(locked):
        raise ThicknessDistributeError('Несогласованные списки толщин и блокировок.')
    if not thicknesses:
        raise ThicknessDistributeError('Нет слоёв для расчёта.')
    if target_total is None or target_total <= 0:
        raise ThicknessDistributeError('Укажите целевую общую толщину больше 0.')

    quant = Decimal('1').scaleb(-decimals)
    result: list[float] = []
    unlocked_indexes: list[int] = []
    locked_sum = Decimal('0')

    for index, (raw_thickness, is_locked) in enumerate(zip(thicknesses, locked, strict=True)):
        current = Decimal(str(raw_thickness or 0))
        if is_locked:
            if current < 0:
                raise ThicknessDistributeError('Зафиксированная толщина не может быть отрицательной.')
            locked_sum += current
            result.append(float(current))
        else:
            result.append(0.0)
            unlocked_indexes.append(index)

    if not unlocked_indexes:
        raise ThicknessDistributeError('Все слои зафиксированы — нечего пересчитывать.')

    remaining = Decimal(str(target_total)) - locked_sum
    if remaining < 0:
        raise ThicknessDistributeError(
            'Сумма зафиксированных толщин больше целевой общей толщины.',
        )
    if remaining == 0:
        raise ThicknessDistributeError(
            'На незафиксированные слои не осталось толщины.',
        )

    share = (remaining / Decimal(len(unlocked_indexes))).quantize(
        quant,
        rounding=ROUND_HALF_UP,
    )
    assigned = Decimal('0')
    for position, index in enumerate(unlocked_indexes):
        if position == len(unlocked_indexes) - 1:
            value = (remaining - assigned).quantize(quant, rounding=ROUND_HALF_UP)
        else:
            value = share
            assigned += value
        result[index] = float(value)
    return result
