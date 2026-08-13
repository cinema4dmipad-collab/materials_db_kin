"""Symmetric composite layups: store the defining half, expand for display."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence


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
