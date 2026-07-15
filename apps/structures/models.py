import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.structures.colors import DEFAULT_STRUCTURE_DISPLAY_COLOR, STRUCTURE_DISPLAY_COLOR_CHOICES
from apps.structures.constants import DEFAULT_DECIMAL_PLACES
from apps.workspaces.visibility import VisibilityMode, WorkspaceVisibilityMixin


STRUCTURE_FIELD_LOCK_ERROR = (
    'Нельзя изменять или удалять поля после создания SQL-таблицы.'
)
STRUCTURE_FIELD_CHANGE_LOCK_ERROR = (
    'Нельзя изменять существующие поля после создания SQL-таблицы.'
)
STRUCTURE_FIELD_DELETE_LOCK_ERROR = (
    'Нельзя удалять поля после создания SQL-таблицы.'
)
MATERIAL_LINK_FIELD_TYPE = 'MaterialLink'


class StructureType(WorkspaceVisibilityMixin, models.Model):
    """Тип структуры — метаданные о таблице."""

    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    table_name = models.CharField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    allow_layers = models.BooleanField(
        default=False,
        verbose_name='Добавить слои',
        help_text='Разрешить добавление слоёв композита для материалов этого типа.',
    )
    display_color = models.CharField(
        max_length=20,
        choices=STRUCTURE_DISPLAY_COLOR_CHOICES,
        default=DEFAULT_STRUCTURE_DISPLAY_COLOR,
        verbose_name='Цвет в интерфейсе',
        help_text='Отображается в списке материалов и карточках с этим типом структуры.',
    )
    is_active = models.BooleanField(default=True)
    is_created = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_structure_types',
        verbose_name='Создал',
    )
    home_workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='home_structure_types',
        verbose_name='Домашнее пространство',
    )
    visibility_mode = models.CharField(
        max_length=32,
        choices=VisibilityMode.choices,
        default=VisibilityMode.ALL_WORKSPACES,
        verbose_name='Режим видимости',
    )
    published_workspaces = models.ManyToManyField(
        'workspaces.Workspace',
        blank=True,
        related_name='published_structure_types',
        verbose_name='Опубликовано в пространствах',
    )

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

    def _raise_if_locked_queryset(self, *, for_delete=False):
        if self.filter(structure_type__is_created=True).exists():
            raise ValidationError(
                STRUCTURE_FIELD_DELETE_LOCK_ERROR
                if for_delete
                else STRUCTURE_FIELD_CHANGE_LOCK_ERROR
            )

    def _raise_if_existing_locked(self, objs):
        object_list = list(objs)
        pks = [obj.pk for obj in object_list if obj.pk]
        if pks and self.model.objects.filter(
            pk__in=pks, structure_type__is_created=True
        ).exists():
            raise ValidationError(STRUCTURE_FIELD_CHANGE_LOCK_ERROR)
        return object_list

    def update(self, **kwargs):
        self._raise_if_locked_queryset(for_delete=False)
        if 'structure_type' in kwargs:
            structure_type = kwargs['structure_type']
            structure_type_id = getattr(structure_type, 'pk', structure_type)
            if self._locked_structure_type_ids([structure_type_id]):
                raise ValidationError(STRUCTURE_FIELD_CHANGE_LOCK_ERROR)
        if 'structure_type_id' in kwargs and self._locked_structure_type_ids(
            [kwargs['structure_type_id']]
        ):
            raise ValidationError(STRUCTURE_FIELD_CHANGE_LOCK_ERROR)
        return super().update(**kwargs)

    def delete(self):
        self._raise_if_locked_queryset(for_delete=True)
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        from apps.structures.sql_executor import SQLExecutor

        object_list = list(objs)
        created = super().bulk_create(object_list, **kwargs)
        for obj in created:
            if not self._locked_structure_type_ids([obj.structure_type_id]):
                continue
            result = SQLExecutor.add_column(obj.structure_type, obj)
            if not result.get('success'):
                raise ValidationError(
                    result.get('error') or 'Не удалось добавить колонку в SQL-таблицу.'
                )
        return created

    def bulk_update(self, objs, fields, **kwargs):
        object_list = self._raise_if_existing_locked(objs)
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
        (MATERIAL_LINK_FIELD_TYPE, 'Материал'),
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
    decimal_places = models.IntegerField(null=True, blank=True, default=DEFAULT_DECIMAL_PLACES)
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

    _LOCKABLE_FIELDS = (
        'name',
        'label',
        'field_type',
        'is_required',
        'default_value',
        'help_text',
        'sort_order',
        'max_digits',
        'decimal_places',
        'max_length',
        'foreign_key_model',
        'structure_type_id',
    )

    def _structure_type_is_created(self):
        if self.structure_type_id and StructureType.objects.filter(
            pk=self.structure_type_id, is_created=True
        ).exists():
            return True
        if self.pk and StructureField.objects.filter(
            pk=self.pk, structure_type__is_created=True
        ).exists():
            return True
        return False

    def _is_dirty_vs_database(self):
        if not self.pk:
            return True
        db_values = (
            StructureField.objects.filter(pk=self.pk)
            .values(*self._LOCKABLE_FIELDS)
            .first()
        )
        if db_values is None:
            return True
        for field_name, db_value in db_values.items():
            if getattr(self, field_name) != db_value:
                return True
        return False

    def clean(self):
        super().clean()
        if (
            self.pk
            and self._structure_type_is_created()
            and self._is_dirty_vs_database()
        ):
            raise ValidationError(STRUCTURE_FIELD_CHANGE_LOCK_ERROR)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()
        super().save(*args, **kwargs)
        if is_new and self._structure_type_is_created():
            from apps.structures.sql_executor import SQLExecutor

            result = SQLExecutor.add_column(self.structure_type, self)
            if not result.get('success'):
                raise ValidationError(
                    result.get('error') or 'Не удалось добавить колонку в SQL-таблицу.'
                )

    def delete(self, *args, **kwargs):
        if self._structure_type_is_created():
            raise ValidationError(STRUCTURE_FIELD_DELETE_LOCK_ERROR)
        return super().delete(*args, **kwargs)

