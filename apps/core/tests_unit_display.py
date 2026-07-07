from django.test import SimpleTestCase

from apps.core.unit_display import looks_like_unit, split_label_and_unit


class UnitDisplayTests(SimpleTestCase):
    def test_split_label_and_unit_parses_percent(self):
        base, unit = split_label_and_unit('Объемное содержание волокна, %')
        self.assertEqual(base, 'Объемное содержание волокна')
        self.assertEqual(unit, '%')

    def test_split_label_and_unit_parses_mm(self):
        base, unit = split_label_and_unit('Толщина, mm')
        self.assertEqual(base, 'Толщина')
        self.assertEqual(unit, 'mm')

    def test_split_label_and_unit_keeps_plain_label(self):
        base, unit = split_label_and_unit('Title')
        self.assertEqual(base, 'Title')
        self.assertEqual(unit, '')

    def test_looks_like_unit_rejects_phrase_after_comma(self):
        self.assertFalse(looks_like_unit('bar and baz'))
