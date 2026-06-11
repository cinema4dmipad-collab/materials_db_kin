from apps.core.sequenced_title import default_sequenced_title
from apps.samples.models import Sample


def default_attachment_title(sample: Sample) -> str:
    titles = sample.attachments.values_list('title', flat=True)
    return default_sequenced_title(sample.name, titles, sample.attachments.count())
