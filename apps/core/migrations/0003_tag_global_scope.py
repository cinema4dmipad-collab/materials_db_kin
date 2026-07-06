import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_tag_workspace'),
        ('workspaces', '0001_initial'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='tag',
            name='unique_tag_slug_per_workspace',
        ),
        migrations.RemoveConstraint(
            model_name='tag',
            name='unique_tag_name_per_workspace',
        ),
        migrations.AlterField(
            model_name='tag',
            name='workspace',
            field=models.ForeignKey(
                blank=True,
                help_text='Пусто — общий тег, доступен во всех пространствах.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='tags',
                to='workspaces.workspace',
                verbose_name='Пространство',
            ),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                condition=Q(('workspace__isnull', True)),
                fields=('slug',),
                name='unique_global_tag_slug',
            ),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                condition=Q(('workspace__isnull', True)),
                fields=('name',),
                name='unique_global_tag_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                condition=Q(('workspace__isnull', False)),
                fields=('workspace', 'slug'),
                name='unique_tag_slug_per_workspace',
            ),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                condition=Q(('workspace__isnull', False)),
                fields=('workspace', 'name'),
                name='unique_tag_name_per_workspace',
            ),
        ),
    ]
