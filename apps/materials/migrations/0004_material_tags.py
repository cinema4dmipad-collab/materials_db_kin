from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_tag'),
        ('materials', '0003_materialattachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='tags',
            field=models.ManyToManyField(
                blank=True,
                related_name='materials',
                to='core.tag',
                verbose_name='Теги',
            ),
        ),
    ]
