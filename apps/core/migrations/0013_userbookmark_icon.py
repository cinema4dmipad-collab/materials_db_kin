from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_userbookmark_page_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='userbookmark',
            name='icon',
            field=models.CharField(
                blank=True,
                help_text='Класс Bootstrap Icons, например bi-bookmark.',
                max_length=64,
                verbose_name='Иконка',
            ),
        ),
    ]
