from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0011_attachment_preview_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='scanrecord',
            name='preview_b_xz',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости XZ.',
                upload_to='scans/previews/%Y/%m/%d/',
                verbose_name='Превью B-скана-XZ',
            ),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='preview_b_yz',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости YZ.',
                upload_to='scans/previews/%Y/%m/%d/',
                verbose_name='Превью B-скана-YZ',
            ),
        ),
        migrations.AlterField(
            model_name='scanrecord',
            name='preview',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) C-скана для списка и карточки.',
                upload_to='scans/previews/%Y/%m/%d/',
                verbose_name='Превью C-скана',
            ),
        ),
    ]
