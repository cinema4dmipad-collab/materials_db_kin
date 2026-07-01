import uuid

from django.conf import settings
from django.db import models


class PropertyGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['sort_order', 'name']


class Property(models.Model):
    DATA_TYPES = [
        ('number', 'Число'),
        ('string', 'Строка'),
        ('boolean', 'Да/Нет'),
        ('date', 'Дата'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=50, blank=True)
    data_type = models.CharField(max_length=20, choices=DATA_TYPES, default='number')
    group = models.ForeignKey(PropertyGroup, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_properties',
        verbose_name='Создал',
    )

    def __str__(self):
        return f"{self.display_name} ({self.unit})" if self.unit else self.display_name

    def label_with_unit(self) -> str:
        display_name = (self.display_name or self.name or '').strip()
        unit = (self.unit or '').strip()
        if unit:
            return f'{display_name}, {unit}'
        return display_name or '\u2014'

    class Meta:
        ordering = ['group__sort_order', 'display_name', 'name']
