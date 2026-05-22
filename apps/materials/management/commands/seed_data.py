from django.core.management.base import BaseCommand
from django.db import transaction

from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property, PropertyGroup


PROPERTY_GROUP = {
    'name': 'Composite material properties',
    'description': 'Core mechanical and physical properties for composite materials.',
    'sort_order': 10,
}

PROPERTIES = [
    {
        'name': 'density',
        'display_name': 'Density',
        'unit': 'g/cm3',
        'data_type': 'number',
        'description': 'Typical cured laminate density.',
    },
    {
        'name': 'tensile_strength',
        'display_name': 'Tensile strength',
        'unit': 'MPa',
        'data_type': 'number',
        'description': 'Representative tensile strength for the composite laminate.',
    },
    {
        'name': 'elastic_modulus',
        'display_name': 'Elastic modulus',
        'unit': 'GPa',
        'data_type': 'number',
        'description': 'Representative tensile elastic modulus.',
    },
]

MATERIALS = [
    {
        'code': 'CMP-CFRP-T700-EP',
        'name': 'CFRP T700 epoxy laminate',
        'description': 'Carbon fiber T700 reinforced epoxy laminate for high-strength parts.',
        'values': {'density': '1.55', 'tensile_strength': '2550', 'elastic_modulus': '135'},
    },
    {
        'code': 'CMP-CFRP-M40J-EP',
        'name': 'CFRP M40J epoxy laminate',
        'description': 'High-modulus M40J carbon fiber epoxy laminate for stiff structures.',
        'values': {'density': '1.60', 'tensile_strength': '1800', 'elastic_modulus': '230'},
    },
    {
        'code': 'CMP-CFRP-HS-EP',
        'name': 'CFRP HS carbon epoxy laminate',
        'description': 'High-strength carbon fiber epoxy laminate, including HC/HS grade analogs.',
        'values': {'density': '1.57', 'tensile_strength': '2200', 'elastic_modulus': '125'},
    },
    {
        'code': 'CMP-CFRP-T800-UD',
        'name': 'CFRP T800 unidirectional epoxy',
        'description': 'Unidirectional T800 carbon epoxy composite for aerospace spars and shells.',
        'values': {'density': '1.58', 'tensile_strength': '2800', 'elastic_modulus': '160'},
    },
    {
        'code': 'CMP-CFRP-WOVEN-EP',
        'name': 'Woven carbon epoxy laminate',
        'description': 'Balanced woven carbon fiber epoxy laminate for panels and covers.',
        'values': {'density': '1.50', 'tensile_strength': '900', 'elastic_modulus': '70'},
    },
    {
        'code': 'CMP-GFRP-EGLASS-EP',
        'name': 'E-glass epoxy laminate',
        'description': 'Electrical-grade glass fiber reinforced epoxy laminate.',
        'values': {'density': '1.95', 'tensile_strength': '850', 'elastic_modulus': '38'},
    },
    {
        'code': 'CMP-GFRP-EGLASS-PE',
        'name': 'E-glass polyester laminate',
        'description': 'General-purpose E-glass fiber polyester composite laminate.',
        'values': {'density': '1.85', 'tensile_strength': '600', 'elastic_modulus': '25'},
    },
    {
        'code': 'CMP-GFRP-SGLASS-EP',
        'name': 'S-glass epoxy laminate',
        'description': 'High-strength S-glass fiber epoxy laminate for loaded components.',
        'values': {'density': '1.98', 'tensile_strength': '1200', 'elastic_modulus': '48'},
    },
    {
        'code': 'CMP-AFRP-KEVLAR-EP',
        'name': 'Kevlar aramid epoxy laminate',
        'description': 'Kevlar/aramid fiber epoxy laminate with high impact resistance.',
        'values': {'density': '1.38', 'tensile_strength': '1400', 'elastic_modulus': '75'},
    },
    {
        'code': 'CMP-BFRP-BASALT-EP',
        'name': 'Basalt fiber epoxy laminate',
        'description': 'Basalt fiber reinforced epoxy laminate for thermally stable structures.',
        'values': {'density': '1.95', 'tensile_strength': '900', 'elastic_modulus': '45'},
    },
    {
        'code': 'CMP-BFRP-BASALT-VE',
        'name': 'Basalt fiber vinyl ester laminate',
        'description': 'Basalt fiber vinyl ester composite for corrosion-resistant applications.',
        'values': {'density': '1.90', 'tensile_strength': '750', 'elastic_modulus': '40'},
    },
    {
        'code': 'CMP-HYB-CARBON-GLASS-EP',
        'name': 'Hybrid carbon-glass epoxy laminate',
        'description': 'Hybrid carbon and glass fiber epoxy laminate balancing stiffness and cost.',
        'values': {'density': '1.72', 'tensile_strength': '1300', 'elastic_modulus': '85'},
    },
]


class Command(BaseCommand):
    help = 'Seeds reference properties and realistic composite material data.'

    def handle(self, *args, **options):
        with transaction.atomic():
            counts = self.seed()

        self.stdout.write(self.style.SUCCESS('Seed data complete.'))
        self.stdout.write(
            'groups: created {created}, updated {updated}'.format(**counts['groups'])
        )
        self.stdout.write(
            'properties: created {created}, updated {updated}'.format(
                **counts['properties']
            )
        )
        self.stdout.write(
            'materials: created {created}, updated {updated}'.format(**counts['materials'])
        )
        self.stdout.write(
            'material properties: created {created}, updated {updated}'.format(
                **counts['material_properties']
            )
        )

    def seed(self):
        counts = {
            'groups': {'created': 0, 'updated': 0},
            'properties': {'created': 0, 'updated': 0},
            'materials': {'created': 0, 'updated': 0},
            'material_properties': {'created': 0, 'updated': 0},
        }

        group, created = PropertyGroup.objects.update_or_create(
            name=PROPERTY_GROUP['name'],
            defaults={
                'description': PROPERTY_GROUP['description'],
                'sort_order': PROPERTY_GROUP['sort_order'],
            },
        )
        self.increment(counts['groups'], created)

        properties = {}
        for property_data in PROPERTIES:
            property_obj, created = Property.objects.update_or_create(
                name=property_data['name'],
                defaults={
                    'display_name': property_data['display_name'],
                    'unit': property_data['unit'],
                    'data_type': property_data['data_type'],
                    'group': group,
                    'description': property_data['description'],
                },
            )
            properties[property_data['name']] = property_obj
            self.increment(counts['properties'], created)

        for material_data in MATERIALS:
            material, created = Material.objects.update_or_create(
                code=material_data['code'],
                defaults={
                    'name': material_data['name'],
                    'description': material_data['description'],
                    'created_by': 'seed_data',
                },
            )
            self.increment(counts['materials'], created)

            for property_name, value in material_data['values'].items():
                _, created = MaterialProperty.objects.update_or_create(
                    material=material,
                    property=properties[property_name],
                    defaults={
                        'value': value,
                        'notes': 'Representative engineering value for seed data.',
                    },
                )
                self.increment(counts['material_properties'], created)

        return counts

    @staticmethod
    def increment(counter, created):
        key = 'created' if created else 'updated'
        counter[key] += 1
