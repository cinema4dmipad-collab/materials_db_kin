from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('composites', '0002_composite_layer_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='compositelayer',
            name='thickness_locked',
            field=models.BooleanField(
                default=False,
                help_text='Зафиксированные слои не меняются при расчёте равных толщин.',
                verbose_name='Толщина зафиксирована',
            ),
        ),
    ]
