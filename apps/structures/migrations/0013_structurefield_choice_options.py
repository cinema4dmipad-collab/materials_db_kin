from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0012_structuretype_created_by_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='structurefield',
            name='choice_options',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Список объектов {"value": "...", "label": "..."} для типа «Выбор из списка».',
                verbose_name='Варианты выбора',
            ),
        ),
        migrations.AlterField(
            model_name='structurefield',
            name='field_type',
            field=models.CharField(
                choices=[
                    ('CharField', 'Строка'),
                    ('TextField', 'Текст'),
                    ('IntegerField', 'Целое число'),
                    ('DecimalField', 'Десятичная дробь'),
                    ('FloatField', 'Число с плавающей точкой'),
                    ('BooleanField', 'Да/Нет'),
                    ('DateField', 'Дата'),
                    ('DateTimeField', 'Дата и время'),
                    ('MaterialLink', 'Материал'),
                    ('ChoiceField', 'Выбор из списка'),
                ],
                max_length=50,
            ),
        ),
    ]
