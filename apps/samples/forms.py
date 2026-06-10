from django import forms
from django.forms import inlineformset_factory

from apps.core.tag_forms import TagNamesFormMixin
from apps.materials.form_widgets import material_select_widget_attrs
from apps.samples.models import Sample, SampleAttachment, SampleProperty
from apps.samples.validators import validate_attachment_file

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}


class SamplePropertyInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = {}
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            prop = form.cleaned_data.get('property')
            if not prop:
                continue
            if prop.pk in seen:
                form.add_error(
                    'property',
                    'Это свойство уже указано в другой строке.',
                )
            else:
                seen[prop.pk] = True


SamplePropertyFormSet = inlineformset_factory(
    Sample,
    SampleProperty,
    fields=['property', 'value'],
    extra=0,
    can_delete=True,
    formset=SamplePropertyInlineFormSet,
    widgets={
        'property': forms.Select(attrs=_BOOTSTRAP_SELECT),
        'value': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
    },
)


class SampleForm(TagNamesFormMixin, forms.ModelForm):
    class Meta:
        model = Sample
        fields = ['code', 'name', 'material', 'object_type', 'created_by']
        labels = {
            'code': 'Код',
            'name': 'Название',
            'material': 'Материал',
            'object_type': 'Тип объекта',
            'created_by': 'Создал',
        }
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'material': forms.Select(attrs=material_select_widget_attrs(
                **{'data-sample-material-select': 'true'},
            )),
            'object_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'created_by': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        }


class SampleAttachmentForm(forms.ModelForm):
    class Meta:
        model = SampleAttachment
        fields = ['file', 'title', 'description']
        labels = {
            'file': 'Файл',
            'title': 'Название',
            'description': 'Описание',
        }

    def __init__(self, *args, optional=False, **kwargs):
        sample = kwargs.pop('sample', None)
        if sample and 'data' not in kwargs:
            kwargs.setdefault('initial', {})['title'] = sample.name
        self.optional = optional
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css_class)
        self.fields['description'].widget.attrs.setdefault('rows', 3)
        if optional and not self.instance.pk:
            self.fields['file'].required = False
            self.fields['title'].required = False

    def has_attachment_data(self):
        return bool(
            self.data.get(self.add_prefix('title'))
            or self.data.get(self.add_prefix('description'))
            or self.files.get(self.add_prefix('file'))
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.optional and not self.instance.pk and not self.has_attachment_data():
            return cleaned_data

        if self.optional and not self.instance.pk:
            if not cleaned_data.get('file'):
                self.add_error('file', 'Выберите файл для загрузки.')
            if not cleaned_data.get('title'):
                self.add_error('title', 'Укажите название файла.')
        return cleaned_data

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            validate_attachment_file(uploaded_file)
        elif self.optional and not self.instance.pk and not self.has_attachment_data():
            return uploaded_file
        elif not self.instance.pk or not self.instance.file:
            raise forms.ValidationError('Выберите файл для загрузки.')
        return uploaded_file
