from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0014_attachment_preview_pdf'),
    ]

    operations = [
        migrations.RenameField(
            model_name='sampleattachment',
            old_name='preview_pdf',
            new_name='preview_image',
        ),
        migrations.AlterField(
            model_name='sampleattachment',
            name='preview_image',
            field=models.FileField(
                blank=True,
                help_text='Миниатюра первой страницы (PNG) для списка вложений.',
                upload_to='sample_attachments/previews/%Y/%m/%d/',
                verbose_name='Превью (изображение)',
            ),
        ),
    ]
