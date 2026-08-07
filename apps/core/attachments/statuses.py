PREVIEW_NONE = 'none'
PREVIEW_SKIPPED = 'skipped'
PREVIEW_PENDING = 'pending'
PREVIEW_READY = 'ready'
PREVIEW_FAILED = 'failed'

PREVIEW_STATUS_CHOICES = [
    (PREVIEW_NONE, 'Нет'),
    (PREVIEW_SKIPPED, 'Не требуется'),
    (PREVIEW_PENDING, 'Обработка'),
    (PREVIEW_READY, 'Готово'),
    (PREVIEW_FAILED, 'Ошибка'),
]
