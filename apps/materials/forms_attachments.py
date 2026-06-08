from django import forms

from apps.materials.models import MaterialAttachment
from apps.samples.validators import validate_attachment_file

_BOOTSTRAP_INPUT = {'class': 'form-control'}


class MaterialAttachmentForm(forms.ModelForm):
    class Meta:
        model = MaterialAttachment
        fields = ['file', 'title', 'description']
        labels = {
            'file': 'Файл',
            'title': 'Название',
            'description': 'Описание',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', _BOOTSTRAP_INPUT['class'])
        self.fields['description'].widget.attrs.setdefault('rows', 3)

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            validate_attachment_file(uploaded_file)
        elif not self.instance.pk or not self.instance.file:
            raise forms.ValidationError('Выберите файл для загрузки.')
        return uploaded_file
