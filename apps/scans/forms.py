from django import forms

from apps.core.tag_forms import TagNamesFormMixin
from apps.scans.models import ScanRecord
from apps.scans.title_utils import default_scan_title
from apps.scans.validators import format_max_scan_file_size, validate_scan_file


class ScanRecordForm(TagNamesFormMixin, forms.ModelForm):
    class Meta:
        model = ScanRecord
        fields = ['file', 'title', 'description', 'method']
        labels = {
            'file': 'Файл HDF5',
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
        if self.instance.pk and self.instance.file:
            self.fields['file'].required = False
            self.fields['file'].help_text = 'Оставьте пустым, чтобы сохранить текущий файл.'

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            validate_scan_file(uploaded_file)
        elif not self.instance.pk or not self.instance.file:
            raise forms.ValidationError('Выберите файл для загрузки.')
        return uploaded_file
