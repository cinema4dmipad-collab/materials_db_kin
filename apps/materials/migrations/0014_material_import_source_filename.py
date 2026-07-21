from django.db import migrations, models


IMPORT_SOURCE_NOTE_PREFIX = 'Создано из файла импорта:'


def forwards_fill_from_description(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    for material in Material.objects.iterator():
        description = material.description or ''
        filename = ''
        kept_lines = []
        for line in description.splitlines():
            stripped = line.strip()
            if stripped.startswith(IMPORT_SOURCE_NOTE_PREFIX):
                if not filename:
                    filename = stripped[len(IMPORT_SOURCE_NOTE_PREFIX) :].strip()
                continue
            kept_lines.append(line)
        cleaned = '\n'.join(kept_lines).strip()
        update_fields = []
        if filename and material.import_source_filename != filename:
            material.import_source_filename = filename
            update_fields.append('import_source_filename')
        if cleaned != description.strip():
            material.description = cleaned
            update_fields.append('description')
        if update_fields:
            material.save(update_fields=update_fields)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0013_alter_material_name_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='import_source_filename',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Имя файла последнего импорта, затронувшего материал.',
                max_length=255,
                verbose_name='Источник импорта',
            ),
        ),
        migrations.RunPython(forwards_fill_from_description, backwards_noop),
    ]
