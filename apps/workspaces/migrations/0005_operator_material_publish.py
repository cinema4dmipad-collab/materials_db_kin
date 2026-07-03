from django.db import migrations


PUBLISH = 'material.publish'


def add_publish_to_operator_groups(apps, schema_editor):
    WorkspaceGroup = apps.get_model('workspaces', 'WorkspaceGroup')
    for group in WorkspaceGroup.objects.filter(is_builtin=True, name='Оператор'):
        permissions = list(group.permissions)
        if PUBLISH not in permissions:
            permissions.append(PUBLISH)
            group.permissions = sorted(permissions)
            group.save(update_fields=['permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0004_workspace_groups'),
    ]

    operations = [
        migrations.RunPython(add_publish_to_operator_groups, migrations.RunPython.noop),
    ]
