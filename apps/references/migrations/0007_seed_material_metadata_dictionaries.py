from django.db import migrations


MANUFACTURERS = [
    ('toray', 'Toray', 10),
    ('hexcel', 'Hexcel', 20),
    ('owens_corning', 'Owens Corning', 30),
    ('steklovolokno', 'Завод Стекловолокно', 40),
]

AVAILABILITIES = [
    ('in_stock', 'В наличии', 10),
    ('on_order', 'Под заказ', 20),
    ('discontinued', 'Снято с производства', 30),
]

TECHNOLOGIES = [
    ('fabric', 'Ткань', 10),
    ('roving', 'Ровинг', 20),
    ('prepreg', 'Препрег', 30),
    ('plastic', 'Пластик', 40),
]


def seed_forward(apps, schema_editor):
    Manufacturer = apps.get_model('references', 'Manufacturer')
    Availability = apps.get_model('references', 'Availability')
    Technology = apps.get_model('references', 'Technology')
    for code, name, sort_order in MANUFACTURERS:
        Manufacturer.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
        )
    for code, name, sort_order in AVAILABILITIES:
        Availability.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
        )
    for code, name, sort_order in TECHNOLOGIES:
        Technology.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
        )


def seed_backward(apps, schema_editor):
    Manufacturer = apps.get_model('references', 'Manufacturer')
    Availability = apps.get_model('references', 'Availability')
    Technology = apps.get_model('references', 'Technology')
    Manufacturer.objects.filter(code__in=[item[0] for item in MANUFACTURERS]).delete()
    Availability.objects.filter(code__in=[item[0] for item in AVAILABILITIES]).delete()
    Technology.objects.filter(code__in=[item[0] for item in TECHNOLOGIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('references', '0006_material_metadata_dictionaries'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
