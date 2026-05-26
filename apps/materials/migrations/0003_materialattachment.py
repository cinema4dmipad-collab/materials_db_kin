import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_structure_link'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaterialAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='material_attachments/%Y/%m/%d/', verbose_name='Файл')),
                ('title', models.CharField(max_length=200, verbose_name='Название')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name='Загружен')),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='materials.material', verbose_name='Материал')),
            ],
            options={
                'verbose_name': 'вложение',
                'verbose_name_plural': 'вложения',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
