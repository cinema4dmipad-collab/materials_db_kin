from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0006_add_materiallink_field_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='structuretype',
            name='allow_layers',
            field=models.BooleanField(
                default=False,
                help_text='Разрешить добавление слоёв композита для материалов этого типа.',
                verbose_name='Добавить слои',
            ),
        ),
    ]
