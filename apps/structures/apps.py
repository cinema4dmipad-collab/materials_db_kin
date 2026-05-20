from django.apps import AppConfig


class StructuresConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.structures'

    def ready(self):
        try:
            import apps.structures.generated_models  # noqa: F401
        except ImportError:
            pass

        import sys

        if any(cmd in sys.argv for cmd in ('migrate', 'makemigrations', 'test')):
            return

        from django.db.models.signals import post_migrate

        def register_dynamic_models(sender, **kwargs):
            from apps.structures.models import StructureType
            from apps.structures.table_generator import TableGenerator

            for structure_type in StructureType.objects.filter(is_created=True):
                if TableGenerator.table_exists(structure_type.table_name):
                    TableGenerator.register_model(structure_type)

        post_migrate.connect(register_dynamic_models, sender=self)
