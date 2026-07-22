# Generated manually for Manufacturer without status/order fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('references', '0007_seed_material_metadata_dictionaries'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='manufacturer',
            options={
                'ordering': ['name'],
                'verbose_name': 'производитель',
                'verbose_name_plural': 'производители',
            },
        ),
        migrations.RemoveField(
            model_name='manufacturer',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='manufacturer',
            name='sort_order',
        ),
    ]
