import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MANAGER_PERMISSIONS = sorted(
    [
        'workspace.view',
        'workspace.manage_settings',
        'workspace.manage_members',
        'material.view',
        'material.create',
        'material.edit',
        'material.delete',
        'material.publish',
        'structure.view',
        'sample.view',
        'sample.create',
        'sample.edit',
        'sample.delete',
        'scan.view',
        'scan.create',
        'scan.edit',
        'scan.delete',
        'property.view',
        'tag.view',
        'tag.create',
        'tag.edit',
        'tag.delete',
    ]
)

OPERATOR_PERMISSIONS = sorted(
    [
        'workspace.view',
        'material.view',
        'material.create',
        'material.edit',
        'structure.view',
        'sample.view',
        'sample.create',
        'sample.edit',
        'scan.view',
        'scan.create',
        'scan.edit',
        'property.view',
        'tag.view',
        'tag.create',
        'tag.edit',
        'tag.delete',
    ]
)


def migrate_memberships_to_groups(apps, schema_editor):
    Workspace = apps.get_model('workspaces', 'Workspace')
    WorkspaceMembership = apps.get_model('workspaces', 'WorkspaceMembership')
    WorkspaceGroup = apps.get_model('workspaces', 'WorkspaceGroup')
    WorkspaceGroupMembership = apps.get_model('workspaces', 'WorkspaceGroupMembership')

    for workspace in Workspace.objects.all():
        manager_group = WorkspaceGroup.objects.create(
            id=uuid.uuid4(),
            workspace=workspace,
            name='Менеджер',
            description='Полный доступ к управлению пространством и данными.',
            permissions=MANAGER_PERMISSIONS,
            is_builtin=True,
        )
        operator_group = WorkspaceGroup.objects.create(
            id=uuid.uuid4(),
            workspace=workspace,
            name='Оператор',
            description='Работа с материалами, образцами и сканами без администрирования.',
            permissions=OPERATOR_PERMISSIONS,
            is_builtin=True,
        )
        for membership in WorkspaceMembership.objects.filter(workspace=workspace):
            group = manager_group if membership.role == 'manager' else operator_group
            WorkspaceGroupMembership.objects.create(
                id=uuid.uuid4(),
                group=group,
                user=membership.user,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0003_fix_membership_uuid_pk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkspaceGroup',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('name', models.CharField(max_length=100, verbose_name='Название')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('permissions', models.JSONField(default=list, verbose_name='Права')),
                ('is_builtin', models.BooleanField(default=False, verbose_name='Встроенная')),
                (
                    'workspace',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='groups',
                        to='workspaces.workspace',
                        verbose_name='Пространство',
                    ),
                ),
            ],
            options={
                'verbose_name': 'группа пространства',
                'verbose_name_plural': 'группы пространств',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='WorkspaceGroupMembership',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'group',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='memberships',
                        to='workspaces.workspacegroup',
                        verbose_name='Группа',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='workspace_group_memberships',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пользователь',
                    ),
                ),
            ],
            options={
                'verbose_name': 'участник группы',
                'verbose_name_plural': 'участники групп',
            },
        ),
        migrations.AddConstraint(
            model_name='workspacegroup',
            constraint=models.UniqueConstraint(
                fields=('workspace', 'name'),
                name='unique_workspace_group_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='workspacegroupmembership',
            constraint=models.UniqueConstraint(
                fields=('group', 'user'),
                name='unique_workspace_group_membership',
            ),
        ),
        migrations.RunPython(migrate_memberships_to_groups, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='WorkspaceMembership',
        ),
    ]
