import uuid

from django.conf import settings
from django.db import models

from apps.core.unit_display import looks_like_unit
from apps.references.constants import DEFAULT_PROPERTY_DECIMAL_PLACES


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
        ('material_link', 'Материал'),
        ('choice', 'Выбор из списка'),
    ]
    MATERIAL_LINK_DATA_TYPE = 'material_link'
    CHOICE_DATA_TYPE = 'choice'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=50, blank=True)
    decimal_places = models.PositiveSmallIntegerField(null=True, blank=True)
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

    def effective_decimal_places(self) -> int | None:
        if self.data_type != 'number':
            return None
        if self.decimal_places is not None:
            return self.decimal_places
        return DEFAULT_PROPERTY_DECIMAL_PLACES

    def effective_unit(self) -> str:
        if self.data_type in {self.MATERIAL_LINK_DATA_TYPE, self.CHOICE_DATA_TYPE}:
            return ''
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

    def choice_options(self):
        return self.choices.order_by('sort_order', 'label', 'value')

    def choice_label_for_value(self, value: str) -> str:
        raw = (value or '').strip()
        if not raw:
            return ''
        for choice in self.choices.all():
            if choice.value == raw:
                return choice.label
        return raw

    class Meta:
        ordering = ['group__sort_order', 'display_name', 'name']


class PropertyChoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='choices',
        verbose_name='Свойство',
    )
    label = models.CharField(max_length=200, verbose_name='Название')
    value = models.CharField(max_length=100, verbose_name='Код')
    sort_order = models.IntegerField(default=0, verbose_name='Порядок')

    class Meta:
        ordering = ['sort_order', 'label', 'value']
        unique_together = [('property', 'value')]
        verbose_name = 'Вариант свойства'
        verbose_name_plural = 'Варианты свойства'

    def __str__(self):
        return f'{self.property.display_name}: {self.label}'
