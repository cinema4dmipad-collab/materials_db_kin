from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0008_scanrecord_uploaded_by_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='scanrecord',
            name='preview',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) для списка сканов.',
                upload_to='scans/previews/%Y/%m/%d/',
                verbose_name='Превью C-скана',
            ),
        ),
    ]
