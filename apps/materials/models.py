import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.references.models import Property


class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    struct_type = models.ForeignKey(
        'structures.StructureType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='Тип структуры',
    )
    struct_props_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='ID параметров структуры',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f'{self.code} - {self.name}'

    def clean(self):
        super().clean()
        if self.struct_props_id and not self.struct_type_id:
            raise ValidationError(
                {'struct_type': 'Выберите тип структуры для параметров структуры.'}
            )
        if not self.struct_type_id or not self.struct_props_id:
            return
        if not self.struct_type.is_created:
            raise ValidationError(
                {'struct_type': 'SQL-таблица для выбранного типа структуры еще не создана.'}
            )
        if self.get_structure_params() is None:
            raise ValidationError(
                {'struct_props_id': 'Запись параметров структуры не найдена.'}
            )

    def get_structure_params(self):
        if not self.struct_type_id or not self.struct_props_id:
            return None

        from apps.structures.sql_executor import SQLExecutor

        return SQLExecutor.get_structure_instance(self.struct_type, self.struct_props_id)

    class Meta:
        ordering = ['code']


class MaterialProperty(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='properties')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='material_values')
    value = models.CharField(max_length=500)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.material.code} - {self.property.display_name}: {self.value}"

    class Meta:
        unique_together = ['material', 'property']
