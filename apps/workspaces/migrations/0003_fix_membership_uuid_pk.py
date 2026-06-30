from django.db import migrations


def upgrade_membership_id_to_uuid(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'workspaces_workspacemembership'
              AND column_name = 'id'
            """
        )
        row = cursor.fetchone()
        if not row or row[0] == 'uuid':
            return

        cursor.execute(
            'ALTER TABLE workspaces_workspacemembership '
            'DROP CONSTRAINT IF EXISTS workspaces_workspacemembership_pkey'
        )
        cursor.execute(
            'ALTER TABLE workspaces_workspacemembership '
            'ALTER COLUMN id DROP IDENTITY IF EXISTS'
        )
        cursor.execute(
            'SELECT pg_get_serial_sequence(%s, %s)',
            ['workspaces_workspacemembership', 'id'],
        )
        sequence_name = cursor.fetchone()[0]
        if sequence_name:
            cursor.execute(f'DROP SEQUENCE IF EXISTS {sequence_name} CASCADE')
        cursor.execute(
            'ALTER TABLE workspaces_workspacemembership '
            'ALTER COLUMN id TYPE uuid USING gen_random_uuid()'
        )
        cursor.execute(
            'ALTER TABLE workspaces_workspacemembership ADD PRIMARY KEY (id)'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0002_alter_workspace_options_and_more'),
    ]

    operations = [
        migrations.RunPython(
            upgrade_membership_id_to_uuid,
            migrations.RunPython.noop,
        ),
    ]
