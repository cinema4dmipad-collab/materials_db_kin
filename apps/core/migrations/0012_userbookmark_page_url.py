from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_backupsettings_interval_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='userbookmark',
            name='url',
            field=models.CharField(
                blank=True,
                help_text='Для закладок типа «Страница» — относительный путь (с query).',
                max_length=2000,
                verbose_name='URL',
            ),
        ),
        migrations.AlterField(
            model_name='userbookmark',
            name='entity_type',
            field=models.CharField(
                choices=[
                    ('material', 'Материал'),
                    ('sample', 'Образец'),
                    ('scan', 'Скан'),
                    ('structure_record', 'Запись структуры'),
                    ('structure_type', 'Тип структуры'),
                    ('page', 'Страница'),
                ],
                max_length=20,
                verbose_name='Тип объекта',
            ),
        ),
    ]
