from django.db import migrations, models


OBJECT_TYPE_MAP = {
    'sample': 'test',
    'prototype': 'test',
    'production': 'product',
}


def migrate_object_types(apps, schema_editor):
    Sample = apps.get_model('samples', 'Sample')
    valid_values = {'unset', 'test', 'control', 'structural_similar', 'product', 'calibration'}
    for sample in Sample.objects.all():
        new_value = OBJECT_TYPE_MAP.get(sample.object_type, sample.object_type)
        if new_value not in valid_values:
            new_value = 'unset'
        if new_value != sample.object_type:
            sample.object_type = new_value
            sample.save(update_fields=['object_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0002_sample_scan_s3'),
    ]

    operations = [
        migrations.RunPython(migrate_object_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='sample',
            name='object_type',
            field=models.CharField(
                choices=[
                    ('unset', 'Не задано'),
                    ('test', 'Испытательный'),
                    ('control', 'Контрольный'),
                    ('structural_similar', 'Конструктивно-подобный'),
                    ('product', 'Изделие'),
                    ('calibration', 'Настроечный'),
                ],
                default='unset',
                max_length=50,
                verbose_name='Тип объекта',
            ),
        ),
    ]
