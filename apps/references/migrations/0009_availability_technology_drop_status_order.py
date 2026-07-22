# Generated manually — drop status/order from Availability and Technology

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('references', '0008_manufacturer_drop_status_order'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='availability',
            options={
                'ordering': ['name'],
                'verbose_name': 'доступность',
                'verbose_name_plural': 'доступность',
            },
        ),
        migrations.AlterModelOptions(
            name='technology',
            options={
                'ordering': ['name'],
                'verbose_name': 'технология',
                'verbose_name_plural': 'технологии',
            },
        ),
        migrations.RemoveField(
            model_name='availability',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='availability',
            name='sort_order',
        ),
        migrations.RemoveField(
            model_name='technology',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='technology',
            name='sort_order',
        ),
    ]
