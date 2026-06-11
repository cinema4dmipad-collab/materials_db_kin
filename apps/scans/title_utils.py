from apps.core.sequenced_title import default_sequenced_title
from apps.samples.models import Sample


def default_scan_title(sample: Sample) -> str:
    titles = sample.scans.values_list('title', flat=True)
    return default_sequenced_title(sample.name, titles, sample.scans.count())
