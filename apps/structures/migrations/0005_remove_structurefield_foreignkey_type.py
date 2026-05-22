from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0004_structurefield_foreign_key_default'),
    ]

    operations = [
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
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='structurefield',
            name='foreign_key_model',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
