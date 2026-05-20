import uuid

from django.db import models

from apps.materials.models import Material


class Sample(models.Model):
    OBJECT_TYPES = [
        ('sample', 'Образец'),
        ('prototype', 'Прототип'),
        ('production', 'Производственная партия'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='samples')
    object_type = models.CharField(max_length=20, choices=OBJECT_TYPES, default='sample')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"
