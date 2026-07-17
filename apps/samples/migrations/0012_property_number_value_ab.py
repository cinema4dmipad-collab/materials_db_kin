from decimal import Decimal, InvalidOperation

from django.db import migrations, models

VALUE_KIND_SCALAR = 'scalar'
VALUE_KIND_RANGE = 'range'
VALUE_KIND_TOLERANCE = 'tolerance'


def _parse_scalar(raw):
    if raw in (None, ''):
        return None
    try:
        return Decimal(str(raw).replace(',', '.'))
    except InvalidOperation:
        return None


def forwards(apps, schema_editor):
    Model = apps.get_model('samples', 'SampleProperty')
    for row in Model.objects.all().iterator():
        kind = (row.value_kind or VALUE_KIND_SCALAR).strip()
        if kind == VALUE_KIND_RANGE:
            row.value_a = row.value_min
            row.value_b = row.value_max
        elif kind == VALUE_KIND_TOLERANCE:
            row.value_a = _parse_scalar(row.value) or row.value_min
            row.value_b = row.value_tolerance
        else:
            row.value_a = row.value_min or _parse_scalar(row.value)
            row.value_b = None
        row.save(update_fields=['value_a', 'value_b'])


def backwards(apps, schema_editor):
    Model = apps.get_model('samples', 'SampleProperty')
    for row in Model.objects.all().iterator():
        kind = (row.value_kind or VALUE_KIND_SCALAR).strip()
        if kind == VALUE_KIND_RANGE:
            row.value_min = row.value_a
            row.value_max = row.value_b
            row.value_tolerance = None
        elif kind == VALUE_KIND_TOLERANCE:
            row.value_min = row.value_a - row.value_b if row.value_a is not None and row.value_b is not None else None
            row.value_max = row.value_a + row.value_b if row.value_a is not None and row.value_b is not None else None
            row.value_tolerance = row.value_b
        else:
            row.value_min = row.value_a
            row.value_max = row.value_a
            row.value_tolerance = None
        row.save(update_fields=['value_min', 'value_max', 'value_tolerance'])


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0011_property_number_tolerance'),
    ]

    operations = [
        migrations.AddField(
            model_name='sampleproperty',
            name='value_a',
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name='sampleproperty',
            name='value_b',
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=18, null=True),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='sampleproperty',
            name='value_max',
        ),
        migrations.RemoveField(
            model_name='sampleproperty',
            name='value_min',
        ),
        migrations.RemoveField(
            model_name='sampleproperty',
            name='value_tolerance',
        ),
    ]
