from apps.core.sequenced_title import default_sequenced_title
from apps.materials.models import Material


def default_material_attachment_title(material: Material) -> str:
    titles = material.attachments.values_list('title', flat=True)
    return default_sequenced_title(material.name, titles, material.attachments.count())
