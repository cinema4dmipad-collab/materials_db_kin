from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0016_sample_structure_params'),
    ]

    operations = [
        migrations.AddField(
            model_name='sample',
            name='description',
            field=models.TextField(blank=True, verbose_name='Описание'),
        ),
    ]
