# Generated manually

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0003_update_object_type_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='SampleAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='sample_attachments/%Y/%m/%d/', verbose_name='Файл')),
                ('title', models.CharField(max_length=200, verbose_name='Название')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.CharField(blank=True, max_length=100, verbose_name='Загрузил')),
                ('sample', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='samples.sample', verbose_name='Образец')),
            ],
            options={
                'verbose_name': 'вложение',
                'verbose_name_plural': 'вложения',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
