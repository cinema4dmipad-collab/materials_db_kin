from django import forms
from django.test import SimpleTestCase
from django.utils.safestring import mark_safe

from apps.core.form_validation import (
    collect_form_errors,
    collect_inline_formset_errors,
    validation_flash_message,
    validation_sections,
)


class ExampleForm(forms.Form):
    name = forms.CharField(label='Название')
    value = forms.IntegerField(label='Значение')


class FormValidationTests(SimpleTestCase):
    def test_collect_form_errors_builds_field_messages(self):
        form = ExampleForm(data={'name': '', 'value': 'abc'})
        self.assertFalse(form.is_valid())

        summary = collect_form_errors(form, default_section='Материал')

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]['section'], 'Материал')
        self.assertIn('Название:', summary[0]['message'])

    def test_collect_form_errors_preserves_safe_html_messages(self):
        form = ExampleForm(data={'name': 'ok', 'value': '1'})
        form.add_error(
            'name',
            mark_safe('Уже есть. <a href="/materials/?scope=shared">Общие</a>.'),
        )

        summary = collect_form_errors(form, default_section='Материал')

        self.assertEqual(len(summary), 1)
        self.assertIn('<a href="/materials/?scope=shared">Общие</a>', summary[0]['message'])
        self.assertNotIn('&lt;a href', summary[0]['message'])

    def test_validation_flash_message_for_single_section(self):
        summary = [{'section': 'Слои композита', 'message': 'Слой 1 — Толщина: ...'}]
        self.assertEqual(
            validation_flash_message(summary),
            'Не удалось сохранить материал. Исправьте ошибки в разделе «Слои композита».',
        )

    def test_validation_flash_message_for_multiple_sections(self):
        summary = [
            {'section': 'Материал', 'message': 'Код: ...'},
            {'section': 'Свойства', 'message': 'Строка 1 — ...'},
        ]
        message = validation_flash_message(summary)
        self.assertIn('Материал', message)
        self.assertIn('Свойства', message)

    def test_collect_inline_formset_errors_includes_row_number(self):
        class InlineForm(forms.Form):
            title = forms.CharField(label='Заголовок')

        invalid_form = InlineForm(data={'title': ''})
        valid_form = InlineForm(data={'title': 'ok'})
        self.assertFalse(invalid_form.is_valid())
        self.assertTrue(valid_form.is_valid())

        class StubFormSet:
            def non_form_errors(self):
                return []

            forms = [invalid_form, valid_form]

        summary = collect_inline_formset_errors(
            StubFormSet(),
            section_label='Слои композита',
            row_label='слой',
        )

        self.assertEqual(len(summary), 1)
        self.assertIn('Слой 1', summary[0]['message'])
        self.assertEqual(summary[0]['section'], 'Слои композита')

    def test_validation_sections_preserves_order(self):
        summary = [
            {'section': 'Свойства', 'message': 'a'},
            {'section': 'Материал', 'message': 'b'},
            {'section': 'Свойства', 'message': 'c'},
        ]
        self.assertEqual(validation_sections(summary), ['Свойства', 'Материал'])
