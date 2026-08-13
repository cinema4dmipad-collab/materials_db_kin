"""Align StructureField decimal_places with the property catalog and SQL scale."""

from __future__ import annotations

from apps.references.models import Property
from apps.structures.models import StructureField, StructureType


def sync_structure_decimal_places_from_catalog(structure_fields) -> list[StructureField]:
    """
    Copy explicit Property.decimal_places onto matching DecimalField rows (by name).

    Bypasses the post-create field lock via QuerySet.update, then widens SQL
    DECIMAL scale when the table already exists.
    """
    decimal_fields = [
        field
        for field in structure_fields
        if getattr(field, 'field_type', None) == 'DecimalField' and field.pk
    ]
    if not decimal_fields:
        return []

    names = [field.name for field in decimal_fields]
    properties_by_name = {
        prop.name: prop
        for prop in Property.objects.filter(
            name__in=names,
            data_type='number',
        ).only('name', 'decimal_places')
        if prop.decimal_places is not None
    }
    if not properties_by_name:
        return []

    from apps.structures.sql_executor import SQLExecutor

    updated: list[StructureField] = []
    for field in decimal_fields:
        prop = properties_by_name.get(field.name)
        if prop is None:
            continue
        places = int(prop.decimal_places)
        if field.decimal_places == places:
            continue
        StructureField.objects.filter(pk=field.pk).update(decimal_places=places)
        field.decimal_places = places
        updated.append(field)

        structure_type = getattr(field, 'structure_type', None)
        if structure_type is None and field.structure_type_id:
            structure_type = StructureType.objects.filter(pk=field.structure_type_id).first()
        if structure_type is not None and structure_type.is_created:
            SQLExecutor.widen_decimal_scale(structure_type, field)

    return updated
