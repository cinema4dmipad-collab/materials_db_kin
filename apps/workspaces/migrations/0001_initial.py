import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Workspace',
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
                ('slug', models.SlugField(unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=200, verbose_name='Название')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активно')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
            ],
            options={
                'verbose_name': 'пространство',
                'verbose_name_plural': 'пространства',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='WorkspaceMembership',
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
                    'role',
                    models.CharField(
                        choices=[('manager', 'Менеджер'), ('operator', 'Оператор')],
                        default='operator',
                        max_length=20,
                        verbose_name='Роль',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='workspace_memberships',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Пользователь',
                    ),
                ),
                (
                    'workspace',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='memberships',
                        to='workspaces.workspace',
                        verbose_name='Пространство',
                    ),
                ),
            ],
            options={
                'verbose_name': 'участник пространства',
                'verbose_name_plural': 'участники пространств',
            },
        ),
        migrations.AddConstraint(
            model_name='workspacemembership',
            constraint=models.UniqueConstraint(
                fields=('workspace', 'user'),
                name='unique_workspace_membership',
            ),
        ),
    ]
