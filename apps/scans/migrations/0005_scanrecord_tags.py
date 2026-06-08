from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_tag'),
        ('scans', '0004_remove_scan_magnification_resolution'),
    ]

    operations = [
        migrations.AddField(
            model_name='scanrecord',
            name='tags',
            field=models.ManyToManyField(
                blank=True,
                related_name='scans',
                to='core.tag',
                verbose_name='Теги',
            ),
        ),
    ]
