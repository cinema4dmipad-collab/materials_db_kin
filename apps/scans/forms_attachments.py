from django import forms

from apps.scans.attachment_title import default_scan_attachment_title
from apps.scans.models import ScanAttachment


class ScanAttachmentForm(forms.ModelForm):
    class Meta:
        model = ScanAttachment
        fields = ['file', 'title', 'description']
        labels = {
            'file': 'Файл',
            'title': 'Название',
            'description': 'Описание',
        }

    def __init__(self, *args, **kwargs):
        scan = kwargs.pop('scan', None)
        if scan and 'data' not in kwargs:
            kwargs.setdefault('initial', {})['title'] = default_scan_attachment_title(scan)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css_class)
        self.fields['description'].widget.attrs.setdefault('rows', 3)
        self.fields['file'].widget.attrs.setdefault(
            'accept',
            '.pdf,.doc,.docx,.odt,.rtf,.xls,.xlsx,.xlsm,.ods,application/pdf',
        )
