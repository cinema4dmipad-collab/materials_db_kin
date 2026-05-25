import uuid

from django.core.exceptions import ValidationError
from django.db import models


class CompositeLayer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_material = models.ForeignKey(
        'materials.Material',
        on_delete=models.CASCADE,
        related_name='composite_layers',
    )
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.PROTECT,
        related_name='used_in_composite_layers',
    )
    layer_number = models.PositiveIntegerField(verbose_name='Номер слоя')
    angle = models.FloatField()
    thickness = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.parent_material.code} layer {self.layer_number}: {self.material.code}'

    def clean(self):
        super().clean()
        if self.parent_material_id and self.parent_material_id == self.material_id:
            raise ValidationError({'material': 'Материал не может быть собственным слоем.'})

    class Meta:
        ordering = ['layer_number']
        unique_together = ['parent_material', 'layer_number']
