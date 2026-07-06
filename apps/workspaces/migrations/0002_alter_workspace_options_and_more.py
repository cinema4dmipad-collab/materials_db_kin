from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='workspace',
            options={
                'ordering': ['name'],
                'verbose_name': 'пространство',
                'verbose_name_plural': 'пространства',
            },
        ),
        migrations.AlterModelOptions(
            name='workspacemembership',
            options={
                'verbose_name': 'участник пространства',
                'verbose_name_plural': 'участники пространств',
            },
        ),
        migrations.AlterUniqueTogether(
            name='workspacemembership',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='workspace',
            name='slug',
            field=models.SlugField(unique=True, verbose_name='Код'),
        ),
    ]
