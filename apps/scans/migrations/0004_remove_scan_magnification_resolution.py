from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0003_rename_scan_type_to_method'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scanrecord',
            name='magnification',
        ),
        migrations.RemoveField(
            model_name='scanrecord',
            name='resolution',
        ),
    ]
