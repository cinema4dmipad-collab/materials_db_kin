from django.db import migrations, models
import django.db.models.deletion


def clear_legacy_scans(apps, schema_editor):
    ScanRecord = apps.get_model('scans', 'ScanRecord')
    ScanRecord.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0002_sample_scan_s3'),
        ('scans', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(clear_legacy_scans, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='scanrecord',
            name='created_at',
        ),
        migrations.RemoveField(
            model_name='scanrecord',
            name='file_path',
        ),
        migrations.RemoveField(
            model_name='scanrecord',
            name='status',
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='file',
            field=models.FileField(upload_to='scans/%Y/%m/%d/', verbose_name='Файл скана'),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='magnification',
            field=models.IntegerField(blank=True, null=True, verbose_name='Увеличение (×)'),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='resolution',
            field=models.CharField(blank=True, max_length=50, verbose_name='Разрешение (dpi)'),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='scan_type',
            field=models.CharField(
                choices=[
                    ('microstructure', 'Микроструктура'),
                    ('spectrum', 'Спектр'),
                    ('surface', 'Поверхность'),
                    ('cross_section', 'Поперечное сечение'),
                    ('other', 'Другое'),
                ],
                default='microstructure',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='uploaded_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='scanrecord',
            name='uploaded_by',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='scanrecord',
            name='uploaded_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
