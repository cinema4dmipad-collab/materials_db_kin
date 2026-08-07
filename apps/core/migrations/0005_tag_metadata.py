from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_tag_created_by_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='color',
            field=models.CharField(
                blank=True,
                help_text='Hex-цвет (#RRGGBB). Пусто — стандартный стиль.',
                max_length=7,
                verbose_name='Цвет',
            ),
        ),
        migrations.AddField(
            model_name='tag',
            name='description',
            field=models.TextField(blank=True, verbose_name='Описание'),
        ),
        migrations.AddField(
            model_name='tag',
            name='is_archived',
            field=models.BooleanField(
                default=False,
                help_text='Скрыт из выбора, но остаётся на уже помеченных записях.',
                verbose_name='В архиве',
            ),
        ),
    ]
