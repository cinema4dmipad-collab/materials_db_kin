from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0005_remove_structurefield_foreignkey_type'),
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
                    ('MaterialLink', 'Материал'),
                ],
                max_length=50,
            ),
        ),
    ]
