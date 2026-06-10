from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_tag'),
        ('samples', '0004_sampleattachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='sample',
            name='tags',
            field=models.ManyToManyField(
                blank=True,
                related_name='samples',
                to='core.tag',
                verbose_name='Теги',
            ),
        ),
    ]
