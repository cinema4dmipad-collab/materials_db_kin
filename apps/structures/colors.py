DEFAULT_STRUCTURE_DISPLAY_COLOR = 'tone-teal'

STRUCTURE_DISPLAY_COLOR_CHOICES = (
    ('tone-coral', 'Коралловый'),
    ('tone-amber', 'Янтарный'),
    ('tone-green', 'Зелёный'),
    ('tone-blue', 'Синий'),
    ('tone-violet', 'Фиолетовый'),
    ('tone-rose', 'Розовый'),
    ('tone-teal', 'Бирюзовый'),
    ('tone-slate', 'Серый'),
)

STRUCTURE_DISPLAY_COLOR_VALUES = frozenset(value for value, _ in STRUCTURE_DISPLAY_COLOR_CHOICES)
