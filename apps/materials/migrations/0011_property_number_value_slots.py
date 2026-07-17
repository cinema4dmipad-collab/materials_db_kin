from django.db import migrations, models


def forwards(apps, schema_editor):
    Model = apps.get_model('materials', 'MaterialProperty')
    for row in Model.objects.all().iterator():
        kind = (row.value_kind or 'scalar').strip()
        if kind == 'range':
            # value_a был min; пишем его в value
            if row.value_a is not None:
                row.value = format(row.value_a, 'f').rstrip('0').rstrip('.') or '0'
        elif kind == 'tolerance':
            if (not row.value) and row.value_a is not None:
                row.value = format(row.value_a, 'f').rstrip('0').rstrip('.') or '0'
        else:
            if (not row.value) and row.value_a is not None:
                row.value = format(row.value_a, 'f').rstrip('0').rstrip('.') or '0'
            row.value_b = None
        row.save(update_fields=['value', 'value_b'])


def backwards(apps, schema_editor):
    from decimal import Decimal, InvalidOperation

    Model = apps.get_model('materials', 'MaterialProperty')
    for row in Model.objects.all().iterator():
        kind = (row.value_kind or 'scalar').strip()
        try:
            primary = Decimal(str(row.value).replace(',', '.')) if row.value else None
        except InvalidOperation:
            primary = None
        row.value_a = primary
        if kind == 'scalar':
            row.value_b = None
        row.save(update_fields=['value_a', 'value_b'])


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0010_property_number_value_ab'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='materialproperty',
            name='value_a',
        ),
    ]
