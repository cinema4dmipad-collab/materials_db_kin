from django.db import migrations, models

import apps.scans.models


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0012_scanrecord_preview_b_scans'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scanrecord',
            name='preview',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) C-скана для списка и карточки.',
                upload_to=apps.scans.models.scan_preview_c_upload_to,
                verbose_name='Превью C-скана',
            ),
        ),
        migrations.AlterField(
            model_name='scanrecord',
            name='preview_b_xz',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости XZ.',
                upload_to=apps.scans.models.scan_preview_b_xz_upload_to,
                verbose_name='Превью B-скана-XZ',
            ),
        ),
        migrations.AlterField(
            model_name='scanrecord',
            name='preview_b_yz',
            field=models.FileField(
                blank=True,
                help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости YZ.',
                upload_to=apps.scans.models.scan_preview_b_yz_upload_to,
                verbose_name='Превью B-скана-YZ',
            ),
        ),
    ]
