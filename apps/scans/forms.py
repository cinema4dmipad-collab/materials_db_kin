from django import forms

from apps.core.tag_forms import TagNamesFormMixin
from apps.scans.models import ScanRecord
from apps.scans.previews import PREVIEW_KINDS
from apps.scans.title_utils import default_scan_title
from apps.scans.validators import (
    format_max_scan_file_size,
    format_max_scan_preview_size,
    validate_scan_file,
    validate_scan_preview,
)


class ScanTagsForm(TagNamesFormMixin, forms.ModelForm):
    """Только теги — для редактирования с карточки скана."""

    class Meta:
        model = ScanRecord
        fields = []


class ScanRecordForm(TagNamesFormMixin, forms.ModelForm):
    class Meta:
        model = ScanRecord
        fields = [
            'title',
            'method',
            'description',
            'file',
            'preview_b_xz',
            'preview_b_yz',
            'preview',
        ]
        labels = {
            'file': 'Файл HDF5',
            'preview': 'Превью C-скана',
            'preview_b_xz': 'Превью B-скана-XZ',
            'preview_b_yz': 'Превью B-скана-YZ',
            'title': 'Название',
            'description': 'Описание',
            'method': 'Метод',
        }

    def __init__(self, *args, **kwargs):
        sample = kwargs.pop('sample', None)
        if sample and 'data' not in kwargs:
            kwargs.setdefault('initial', {})['title'] = default_scan_title(sample)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css_class)
        self.fields['description'].widget.attrs.setdefault('rows', 3)
        max_size = format_max_scan_file_size()
        self.fields['file'].help_text = f'Формат HDF5: файлы .h5 или .hdf5, до {max_size}.'
        self._configure_preview_fields()
        if self.instance.pk and self.instance.file:
            self.fields['file'].required = False
            self.fields['file'].help_text = 'Оставьте пустым, чтобы сохранить текущий файл.'

    def _configure_preview_fields(self):
        size = format_max_scan_preview_size()
        for kind in PREVIEW_KINDS:
            field = self.fields[kind.field]
            field.required = False
            field.widget.attrs.setdefault('accept', 'image/png,image/jpeg,image/webp')
            field.help_text = (
                f'Необязательно. PNG, JPEG или WebP, до {size} — {kind.label}.'
            )
            if self.instance.pk and getattr(self.instance, kind.field):
                field.help_text += ' Оставьте пустым, чтобы сохранить текущее превью.'

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            validate_scan_file(uploaded_file)
        elif not self.instance.pk or not self.instance.file:
            raise forms.ValidationError('Выберите файл для загрузки.')
        return uploaded_file

    def _clean_preview_named(self, name):
        uploaded = self.cleaned_data.get(name)
        if uploaded:
            validate_scan_preview(uploaded)
        return uploaded

    def clean_preview(self):
        return self._clean_preview_named('preview')

    def clean_preview_b_xz(self):
        return self._clean_preview_named('preview_b_xz')

    def clean_preview_b_yz(self):
        return self._clean_preview_named('preview_b_yz')
