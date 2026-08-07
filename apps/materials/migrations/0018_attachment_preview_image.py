from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0017_attachment_preview_pdf'),
    ]

    operations = [
        migrations.RenameField(
            model_name='materialattachment',
            old_name='preview_pdf',
            new_name='preview_image',
        ),
        migrations.AlterField(
            model_name='materialattachment',
            name='preview_image',
            field=models.FileField(
                blank=True,
                help_text='Миниатюра первой страницы (PNG) для списка вложений.',
                upload_to='material_attachments/previews/%Y/%m/%d/',
                verbose_name='Превью (изображение)',
            ),
        ),
    ]
