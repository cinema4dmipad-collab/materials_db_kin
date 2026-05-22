from django.db import migrations, models


def backfill_blank_foreign_key_model(apps, schema_editor):
    StructureField = apps.get_model('structures', 'StructureField')
    StructureField.objects.filter(
        field_type='ForeignKey',
        foreign_key_model='',
    ).update(foreign_key_model='materials.Material')


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0003_dynamic_tables'),
    ]

    operations = [
        migrations.RunPython(
            backfill_blank_foreign_key_model,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='structurefield',
            name='foreign_key_model',
            field=models.CharField(
                blank=True,
                default='materials.Material',
                max_length=200,
            ),
        ),
    ]
