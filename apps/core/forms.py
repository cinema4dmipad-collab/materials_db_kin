from datetime import time

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import BackupSettings, Tag
from apps.core.tag_utils import (
    normalize_tag_name,
    tag_slug_from_name,
    validate_tag_color,
    validate_tag_names,
)

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_TEXTAREA = {'class': 'form-control', 'rows': 3}
_BOOTSTRAP_CHECKBOX = {'class': 'form-check-input'}


class BackupSettingsForm(forms.ModelForm):
    schedule_time = forms.TimeField(
        label='Время запуска',
        widget=forms.TimeInput(attrs={**_BOOTSTRAP_INPUT, 'type': 'time'}, format='%H:%M'),
        input_formats=['%H:%M', '%H:%M:%S'],
        help_text='Ежедневный запуск по локальному времени сервера.',
    )

    class Meta:
        model = BackupSettings
        fields = ['enabled', 'retention_count']
        widgets = {
            'enabled': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
            'retention_count': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 1}),
        }
        labels = {
            'enabled': 'Авто копирование',
            'retention_count': 'Количество хранимых копий',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance') or getattr(self, 'instance', None)
        if instance and instance.pk:
            self.fields['schedule_time'].initial = time(
                hour=instance.schedule_hour,
                minute=instance.schedule_minute,
            )

    def save(self, commit=True):
        settings = super().save(commit=False)
        schedule_time = self.cleaned_data['schedule_time']
        settings.schedule_hour = schedule_time.hour
        settings.schedule_minute = schedule_time.minute
        if commit:
            settings.save()
        return settings


class BackupRestoreForm(forms.Form):
    server_dump = forms.ChoiceField(
        label='Файл на сервере (/backups)',
        required=False,
        widget=forms.Select(attrs=_BOOTSTRAP_INPUT),
        help_text='Предпочтительно: дамп уже лежит на сервере — без загрузки через браузер.',
    )
    dump_file = forms.FileField(
        label='Или загрузить .dump с компьютера',
        required=False,
        help_text=(
            'Если Chrome пишет ERR_UPLOAD_FILE_CHANGED — скопируйте файл на рабочий стол '
            'и выберите копию (не из Downloads, пока идёт/висела загрузка).'
        ),
        widget=forms.FileInput(attrs={**_BOOTSTRAP_INPUT, 'accept': '.dump,application/octet-stream'}),
    )
    confirm = forms.BooleanField(
        label='Понимаю: текущие данные БД будут заменены содержимым дампа',
        required=True,
        widget=forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
    )

    def __init__(self, *args, server_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', '— не выбран —'), *(server_choices or [])]
        self.fields['server_dump'].choices = choices

    def clean_dump_file(self):
        from django.conf import settings as django_settings

        uploaded = self.cleaned_data.get('dump_file')
        if not uploaded:
            return uploaded
        name = (uploaded.name or '').lower()
        if not name.endswith('.dump'):
            raise ValidationError('Ожидается файл с расширением .dump.')
        max_bytes = getattr(django_settings, 'BACKUP_UPLOAD_MAX_BYTES', 512 * 1024 * 1024)
        if uploaded.size and uploaded.size > max_bytes:
            raise ValidationError(
                f'Файл слишком большой (макс. {max_bytes // (1024 * 1024)} МБ). '
                'Скопируйте дамп на сервер в /backups и выберите его в списке выше.'
            )
        return uploaded

    def clean(self):
        cleaned = super().clean()
        server_dump = (cleaned.get('server_dump') or '').strip()
        dump_file = cleaned.get('dump_file')
        if server_dump and dump_file:
            raise ValidationError('Выберите либо файл на сервере, либо загрузку с компьютера — не оба сразу.')
        if not server_dump and not dump_file:
            raise ValidationError('Укажите файл на сервере или загрузите .dump с компьютера.')
        return cleaned


class TagForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        label='Общий тег',
        help_text='Доступен во всех пространствах.',
        widget=forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
    )

    def __init__(self, *args, workspace=None, allow_global=False, **kwargs):
        self.workspace = workspace
        self.allow_global = allow_global
        super().__init__(*args, **kwargs)
        if not allow_global:
            self.fields.pop('is_global', None)
        elif self.instance.pk and not self.instance._state.adding and self.instance.is_global:
            self.fields['is_global'].initial = True
            self.fields['is_global'].disabled = True
        else:
            self.fields['is_global'].initial = False
        self.fields['color'].widget = forms.TextInput(
            attrs={**_BOOTSTRAP_INPUT, 'placeholder': '#336699', 'maxlength': '7'},
        )

    class Meta:
        model = Tag
        fields = ['name', 'description', 'color', 'is_archived']
        widgets = {
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs=_BOOTSTRAP_TEXTAREA),
            'is_archived': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
        }
        labels = {
            'name': 'Название',
            'description': 'Описание',
            'color': 'Цвет',
            'is_archived': 'В архиве',
        }
        help_texts = {
            'name': (
                'Уникально в пределах области тега. '
                'Для взаимоисключающих меток используйте «область::значение».'
            ),
            'description': 'Когда и зачем ставить этот тег.',
            'is_archived': 'Скрывает тег из выбора, но сохраняет на уже помеченных записях.',
        }

    def clean_name(self):
        name = normalize_tag_name(self.cleaned_data.get('name', ''))
        if not name:
            raise ValidationError('Укажите название тега.')
        validate_tag_names([name])
        return name

    def clean_color(self):
        color = (self.cleaned_data.get('color') or '').strip()
        validate_tag_color(color)
        return color.upper() if color else ''

    def clean_is_global(self):
        if not self.allow_global:
            return False
        if self.instance.pk and not self.instance._state.adding and self.instance.is_global:
            return True
        return bool(self.cleaned_data.get('is_global'))

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        if not name:
            return cleaned_data

        is_global = cleaned_data.get('is_global', False)
        slug = tag_slug_from_name(name)
        if is_global:
            queryset = Tag.objects.filter(slug=slug, workspace__isnull=True)
        elif self.workspace is None:
            self.add_error('name', 'Выберите активное пространство для тега пространства.')
            return cleaned_data
        else:
            queryset = Tag.objects.filter(slug=slug, workspace=self.workspace)

        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            existing = queryset.first()
            scope = 'глобальных тегов' if is_global else 'этого пространства'
            self.add_error('name', f'Тег «{existing.name}» уже существует среди {scope}.')
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = tag_slug_from_name(instance.name)
        is_global = self.cleaned_data.get('is_global', False)
        if is_global:
            instance.workspace = None
        elif self.workspace is not None:
            instance.workspace = self.workspace
        if commit:
            instance.save()
        return instance
