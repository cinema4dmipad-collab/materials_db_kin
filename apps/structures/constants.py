DEFAULT_MAX_DIGITS = 10
DEFAULT_DECIMAL_PLACES = 2
STRUCTURE_FIELD_PREFIX = 'structure_field_'


def resolve_decimal_places(value, default: int = DEFAULT_DECIMAL_PLACES) -> int:
    """Return decimal places; treat only None/'' as missing (0 is valid)."""
    if value is None or value == '':
        return default
    return int(value)


def resolve_structure_field_decimal_places(structure_field, *, properties_by_name: dict | None = None) -> int:
    """Prefer explicit Property.decimal_places (same name); else StructureField."""
    prop = None
    if properties_by_name is not None:
        prop = properties_by_name.get(structure_field.name)
    else:
        from apps.references.models import Property

        prop = (
            Property.objects.filter(
                name=structure_field.name,
                data_type='number',
            )
            .only('decimal_places')
            .first()
        )
    if prop is not None and prop.decimal_places is not None:
        return int(prop.decimal_places)
    return resolve_decimal_places(getattr(structure_field, 'decimal_places', None))