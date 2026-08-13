from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0018_attachment_preview_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='layers_symmetric',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'В таблице задаётся первая половина слоёв (при нечёте последний — центральный); '
                    'вторая половина зеркалируется в превью и на карточке.'
                ),
                verbose_name='Симметричная укладка',
            ),
        ),
    ]
