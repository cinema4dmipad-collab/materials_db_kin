import uuid

from django.conf import settings
from django.db import models

from apps.core.unit_display import looks_like_unit


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

    def effective_unit(self) -> str:
        unit = (self.unit or '').strip()
        if unit:
            return unit
        display_name = (self.display_name or '').strip()
        if ', ' not in display_name:
            return ''
        candidate = display_name.rsplit(', ', 1)[-1].strip()
        if looks_like_unit(candidate):
            return candidate
        return ''

    def base_display_name(self) -> str:
        display_name = (self.display_name or self.name or '').strip()
        unit = self.effective_unit()
        if unit and display_name.endswith(f', {unit}'):
            return display_name[: -len(f', {unit}')].strip()
        return display_name or '\u2014'

    def label_with_unit(self) -> str:
        display_name = self.base_display_name()
        if display_name == '\u2014':
            return display_name
        unit = self.effective_unit()
        if unit:
            return f'{display_name}, {unit}'
        return display_name

    class Meta:
        ordering = ['group__sort_order', 'display_name', 'name']
