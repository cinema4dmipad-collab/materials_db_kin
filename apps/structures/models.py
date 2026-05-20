import uuid

from django.db import models


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
        ('ForeignKey', 'Связь с другой моделью'),
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
    foreign_key_model = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['sort_order']
        unique_together = ['structure_type', 'name']

    def __str__(self):
        return f'{self.structure_type.name}.{self.name}'


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
        if field_type in ('CharField', 'TextField', 'ForeignKey'):
            if field_type == 'ForeignKey' and self.value_fk_id:
                return str(self.value_fk_id)
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
