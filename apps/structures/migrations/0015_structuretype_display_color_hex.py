from django.db import migrations, models

from apps.structures.colors import DEFAULT_STRUCTURE_DISPLAY_COLOR, TONE_TO_HEX


def convert_tone_colors_to_hex(apps, schema_editor):
    StructureType = apps.get_model('structures', 'StructureType')
    for structure_type in StructureType.objects.all():
        color = structure_type.display_color or ''
        hex_color = TONE_TO_HEX.get(color, color)
        if hex_color != color:
            structure_type.display_color = hex_color
            structure_type.save(update_fields=['display_color'])


class Migration(migrations.Migration):

    dependencies = [
        ('structures', '0014_alter_structurefield_decimal_places_default'),
    ]

    operations = [
        migrations.RunPython(convert_tone_colors_to_hex, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='structuretype',
            name='display_color',
            field=models.CharField(
                default=DEFAULT_STRUCTURE_DISPLAY_COLOR,
                help_text='Hex-цвет (#RRGGBB) для бейджей материалов и карточек с этим типом структуры.',
                max_length=7,
                verbose_name='Цвет в интерфейсе',
            ),
        ),
    ]
