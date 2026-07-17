from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0010_property_number_range'),
    ]

    operations = [
        migrations.AddField(
            model_name='sampleproperty',
            name='value_tolerance',
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=18, null=True),
        ),
        migrations.AlterField(
            model_name='sampleproperty',
            name='value_kind',
            field=models.CharField(
                choices=[
                    ('scalar', 'Точное'),
                    ('range', 'Диапазон'),
                    ('tolerance', '± погрешность'),
                ],
                default='scalar',
                max_length=10,
            ),
        ),
    ]
