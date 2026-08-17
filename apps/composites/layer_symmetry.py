"""Symmetric composite layups: store the defining half, expand for display."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence


def mirrored_layer_count(defining_count: int) -> int:
    """How many layers the mirror half adds (0 for a single central ply)."""
    if defining_count <= 0:
        return 0
    if defining_count % 2 == 0:
        return defining_count
    return defining_count - 1


def format_layer_count_label(defining_count: int, *, symmetric: bool = False) -> str:
    if defining_count <= 0:
        return ''
    if not symmetric:
        return f'{defining_count} сл.'
    mirror_count = mirrored_layer_count(defining_count)
    if mirror_count <= 0:
        return f'{defining_count} сл.'
    return f'{defining_count} сл. (+ {mirror_count} сим. слоёв)'


def format_mirror_note(defining_count: int) -> str:
    mirror_count = mirrored_layer_count(defining_count)
    if mirror_count <= 0:
        return ''
    return f'+ {mirror_count} симметричных слоёв'


def expand_symmetric_sequence(items: Sequence):
    """
    Even n: [1..n] + reverse([1..n]).
    Odd n: [1..n-1] + [center=n] + reverse([1..n-1]).
    """
    values = list(items)
    if not values:
        return []
    if len(values) % 2 == 0:
        return values + list(reversed(values))
    side = values[:-1]
    center = values[-1]
    return side + [center] + list(reversed(side))


def expand_symmetric_layer_objects(layers: Sequence) -> list:
    """Expand stored layers for detail/diagram; renumber 1..N."""
    expanded = expand_symmetric_sequence(list(layers))
    result = []
    for index, layer in enumerate(expanded, start=1):
        result.append(
            SimpleNamespace(
                layer_number=index,
                material_id=layer.material_id,
                material=layer.material,
                angle=layer.angle,
                thickness=layer.thickness,
                thickness_locked=getattr(layer, 'thickness_locked', False),
            )
        )
    return result
