from django.db import migrations


def create_composite_layer_table(apps, schema_editor):
    connection = schema_editor.connection
    tables = connection.introspection.table_names()

    if 'composites_composite' in tables:
        schema_editor.execute('DROP TABLE composites_composite CASCADE')

    if 'composites_compositelayer' in tables:
        return

    CompositeLayer = apps.get_model('composites', 'CompositeLayer')
    schema_editor.create_model(CompositeLayer)


def drop_composite_layer_table(apps, schema_editor):
    connection = schema_editor.connection
    tables = connection.introspection.table_names()

    if 'composites_compositelayer' in tables:
        CompositeLayer = apps.get_model('composites', 'CompositeLayer')
        schema_editor.delete_model(CompositeLayer)


class Migration(migrations.Migration):

    dependencies = [
        ('composites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            create_composite_layer_table,
            drop_composite_layer_table,
        ),
    ]
