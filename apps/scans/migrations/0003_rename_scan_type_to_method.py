from django.db import migrations, models


def migrate_scan_type_to_method(apps, schema_editor):
    ScanRecord = apps.get_model('scans', 'ScanRecord')
    ScanRecord.objects.exclude(scan_type__in=['echo', 'shadow', 'immersion']).update(scan_type='echo')


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0002_sample_scan_s3'),
    ]

    operations = [
        migrations.RunPython(migrate_scan_type_to_method, migrations.RunPython.noop),
        migrations.RenameField(
            model_name='scanrecord',
            old_name='scan_type',
            new_name='method',
        ),
        migrations.AlterField(
            model_name='scanrecord',
            name='method',
            field=models.CharField(
                choices=[
                    ('echo', 'Эхо'),
                    ('shadow', 'Теневой'),
                    ('immersion', 'Иммерсивный'),
                ],
                default='echo',
                max_length=50,
                verbose_name='Метод',
            ),
        ),
    ]
