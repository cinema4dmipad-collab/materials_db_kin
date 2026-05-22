import uuid

from django.core.exceptions import ValidationError
from django.db import models


STRUCTURE_FIELD_LOCK_ERROR = (
    'Нельзя добавлять, изменять или удалять поля после создания SQL-таблицы.'
)


class StructureType(models.Model):
    """Тип структуры — метаданные о таблице."""

    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    table_name = models.CharField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_created = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.table_name:
            self.table_name = f'structures_{self.code}'.replace('-', '_')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class StructureFieldQuerySet(models.QuerySet):
    def _locked_structure_type_ids(self, structure_type_ids):
        ids = {structure_type_id for structure_type_id in structure_type_ids if structure_type_id}
        if not ids:
            return set()
        return set(
            StructureType.objects.filter(pk__in=ids, is_created=True).values_list(
                'pk', flat=True
            )
        )

    def _raise_if_locked_queryset(self):
        if self.filter(structure_type__is_created=True).exists():
            raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)

    def _raise_if_locked_objects(self, objs, include_existing=False):
        object_list = list(objs)
        locked_ids = self._locked_structure_type_ids(
            obj.structure_type_id for obj in object_list
        )
        if locked_ids:
            raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)

        if include_existing:
            pks = [obj.pk for obj in object_list if obj.pk]
            if pks and self.model.objects.filter(
                pk__in=pks, structure_type__is_created=True
            ).exists():
                raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)

        return object_list

    def update(self, **kwargs):
        self._raise_if_locked_queryset()
        if 'structure_type' in kwargs:
            structure_type = kwargs['structure_type']
            structure_type_id = getattr(structure_type, 'pk', structure_type)
            if self._locked_structure_type_ids([structure_type_id]):
                raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)
        if 'structure_type_id' in kwargs and self._locked_structure_type_ids(
            [kwargs['structure_type_id']]
        ):
            raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)
        return super().update(**kwargs)

    def delete(self):
        self._raise_if_locked_queryset()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        object_list = self._raise_if_locked_objects(objs)
        return super().bulk_create(object_list, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        object_list = self._raise_if_locked_objects(objs, include_existing=True)
        return super().bulk_update(object_list, fields, **kwargs)


class StructureFieldManager(models.Manager.from_queryset(StructureFieldQuerySet)):
    pass


class StructureField(models.Model):
    """Поле для конкретного типа структуры"""

    FIELD_TYPES = [
        ('CharField', 'Строка'),
        ('TextField', 'Текст'),
        ('IntegerField', 'Целое число'),
        ('DecimalField', 'Десятичная дробь'),
        ('FloatField', 'Число с плавающей точкой'),
        ('BooleanField', 'Да/Нет'),
        ('DateField', 'Дата'),
        ('DateTimeField', 'Дата и время'),
    ]

    structure_type = models.ForeignKey(
        StructureType, on_delete=models.CASCADE, related_name='fields'
    )
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=500, blank=True)
    help_text = models.CharField(max_length=500, blank=True)
    sort_order = models.IntegerField(default=0)
    max_digits = models.IntegerField(null=True, blank=True, default=10)
    decimal_places = models.IntegerField(null=True, blank=True, default=2)
    max_length = models.IntegerField(null=True, blank=True, default=255)
    foreign_key_model = models.CharField(
        max_length=200,
        blank=True,
        default='',
    )

    objects = StructureFieldManager()

    class Meta:
        ordering = ['sort_order']
        unique_together = ['structure_type', 'name']

    def __str__(self):
        return f'{self.structure_type.name}.{self.name}'

    def _has_locked_structure_type(self):
        if self.structure_type_id and StructureType.objects.filter(
            pk=self.structure_type_id, is_created=True
        ).exists():
            return True
        if self.pk and StructureField.objects.filter(
            pk=self.pk, structure_type__is_created=True
        ).exists():
            return True
        return False

    def clean(self):
        super().clean()
        if self._has_locked_structure_type():
            raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._has_locked_structure_type():
            raise ValidationError(STRUCTURE_FIELD_LOCK_ERROR)
        return super().delete(*args, **kwargs)


class StructureInstance(models.Model):
    """Экземпляр конкретной структуры"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    structure_type = models.ForeignKey(StructureType, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, unique=True)
    dynamic_row_id = models.UUIDField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.structure_type.name}: {self.code}'


class StructureFieldValue(models.Model):
    """Значение поля для экземпляра структуры"""

    instance = models.ForeignKey(
        StructureInstance, on_delete=models.CASCADE, related_name='values'
    )
    field = models.ForeignKey(StructureField, on_delete=models.CASCADE)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    value_integer = models.IntegerField(null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_fk_id = models.UUIDField(null=True, blank=True)

    class Meta:
        unique_together = ['instance', 'field']

    def get_value(self):
        field_type = self.field.field_type
        if field_type in ('CharField', 'TextField'):
            return self.value_text
        if field_type == 'IntegerField':
            return self.value_integer
        if field_type in ('DecimalField', 'FloatField'):
            return self.value_number
        if field_type == 'BooleanField':
            return self.value_boolean
        if field_type == 'DateField':
            return self.value_date
        if field_type == 'DateTimeField':
            return self.value_datetime
        return None
