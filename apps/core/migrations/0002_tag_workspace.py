import django.db.models.deletion
from django.db import migrations, models


def assign_legacy_workspace(apps, schema_editor):
    Tag = apps.get_model('core', 'Tag')
    Workspace = apps.get_model('workspaces', 'Workspace')
    legacy = Workspace.objects.filter(slug='legacy').first()
    if legacy is None:
        legacy = Workspace.objects.create(
            slug='legacy',
            name='Legacy',
            description='Пространство по умолчанию для данных до миграции на workspaces.',
            is_active=True,
        )
    Tag.objects.filter(workspace__isnull=True).update(workspace=legacy)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_tag'),
        ('workspaces', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='workspace',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='tags',
                to='workspaces.workspace',
                verbose_name='Пространство',
            ),
        ),
        migrations.RunPython(assign_legacy_workspace, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='tag',
            name='workspace',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='tags',
                to='workspaces.workspace',
                verbose_name='Пространство',
            ),
        ),
        migrations.AlterField(
            model_name='tag',
            name='name',
            field=models.CharField(max_length=50, verbose_name='Название'),
        ),
        migrations.AlterField(
            model_name='tag',
            name='slug',
            field=models.SlugField(max_length=50, verbose_name='Код'),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                fields=('workspace', 'slug'),
                name='unique_tag_slug_per_workspace',
            ),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                fields=('workspace', 'name'),
                name='unique_tag_name_per_workspace',
            ),
        ),
    ]
