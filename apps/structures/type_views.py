from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, TemplateView, UpdateView, View

from apps.materials.models import Material
from apps.structures.identifiers import validate_table_name
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.type_forms import StructureFieldInlineFormSet, StructureTypeDisplayColorForm, StructureTypeForm


def _apply_posted_table_name(structure_type, raw_table_name: str) -> str | None:
    """Validate POST table_name and save on structure_type. Returns error text or None."""
    raw_table_name = (raw_table_name or '').strip()
    if not raw_table_name:
        return None
    try:
        table_name = validate_table_name(raw_table_name)
    except ValueError as exc:
        return str(exc)
    if (
        StructureType.objects.filter(table_name=table_name)
        .exclude(pk=structure_type.pk)
        .exists()
    ):
        return f'Таблица {table_name} уже используется другим типом.'
    if structure_type.table_name != table_name:
        structure_type.table_name = table_name
        structure_type.save(update_fields=['table_name'])
    return None


class StructureTypeFormsetMixin:
    def get_field_formset(self):
        kwargs = {'prefix': 'fields'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        return StructureFieldInlineFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('field_formset', self.get_field_formset())
        context['reference_properties'] = self.get_reference_properties()
        return context

    def get_reference_properties(self):
        from apps.structures.property_mapping import reference_properties_for_picker

        return reference_properties_for_picker()

    def validate_and_save_formsets(self, form):
        field_formset = self.get_field_formset()
        if not field_formset.is_valid():
            return None, field_formset

        with transaction.atomic():
            self.object = form.save()
            field_formset.instance = self.object
            field_formset.save()
        return self.object, field_formset

    def render_with_formsets(self, form, field_formset):
        return self.render_to_response(
            self.get_context_data(form=form, field_formset=field_formset)
        )


class StructureTypeCreateView(StructureTypeFormsetMixin, CreateView):
    model = StructureType
    form_class = StructureTypeForm
    template_name = 'structures/type_form.html'

    def form_valid(self, form):
        field_formset = self.get_field_formset()
        if not field_formset.is_valid():
            return self.render_with_formsets(form, field_formset)

        try:
            with transaction.atomic():
                self.object = form.save()
                field_formset.instance = self.object
                field_formset.save()
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.render_with_formsets(form, field_formset)

        messages.success(self.request, f'Тип структуры «{self.object.name}» создан.')
        manage_url = reverse('structures:type_manage', kwargs={'type_code': self.object.code})
        return redirect(f'{manage_url}?prompt_create_table=1')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        context['fields_locked'] = False
        return context


class StructureTypeUpdateView(StructureTypeFormsetMixin, UpdateView):
    model = StructureType
    form_class = StructureTypeForm
    template_name = 'structures/type_form.html'
    context_object_name = 'structure_type'
    slug_field = 'code'
    slug_url_kwarg = 'type_code'

    def get_queryset(self):
        return StructureType.objects.filter(is_active=True)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_created:
            messages.info(request, 'После создания SQL-таблицы редактирование полей недоступно.')
            return redirect('structures:type_manage', type_code=self.object.code)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        field_formset = self.get_field_formset()
        if not field_formset.is_valid():
            return self.render_with_formsets(form, field_formset)

        try:
            with transaction.atomic():
                self.object = form.save()
                field_formset.instance = self.object
                field_formset.save()
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.render_with_formsets(form, field_formset)

        messages.success(self.request, 'Тип структуры сохранён.')
        return redirect('structures:type_manage', type_code=self.object.code)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        context['fields_locked'] = self.object.is_created
        return context


class StructureTypeManageView(TemplateView):
    template_name = 'structures/type_manage.html'

    def get_structure_type(self):
        return get_object_or_404(
            StructureType.objects.prefetch_related('fields'),
            code=self.kwargs['type_code'],
            is_active=True,
        )

    def post(self, request, type_code):
        structure_type = self.get_structure_type()
        form = StructureTypeDisplayColorForm(request.POST, instance=structure_type)
        if form.is_valid():
            form.save()
            messages.success(request, 'Цвет типа структуры обновлён.')
        else:
            messages.error(request, 'Не удалось сохранить цвет. Проверьте выбранное значение.')
        return redirect('structures:type_manage', type_code=type_code)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        structure_type = self.get_structure_type()
        context['structure_type'] = structure_type
        context['color_form'] = StructureTypeDisplayColorForm(instance=structure_type)
        context['fields'] = structure_type.fields.all()
        context['can_create_table'] = not structure_type.is_created
        context['can_drop_table'] = structure_type.is_created
        context['linked_materials_count'] = Material.objects.filter(
            struct_type=structure_type,
        ).count()
        context['table_exists'] = (
            structure_type.is_created or SQLExecutor.table_exists(structure_type)
        )
        context['prompt_create_table'] = not structure_type.is_created
        return context


class StructureTypeCreateTableView(View):
    def post(self, request, type_code):
        structure_type = get_object_or_404(
            StructureType.objects.prefetch_related('fields'),
            code=type_code,
            is_active=True,
        )
        if structure_type.is_created:
            messages.warning(request, 'SQL-таблица уже создана.')
            return redirect('structures:type_manage', type_code=type_code)

        table_name_error = _apply_posted_table_name(
            structure_type,
            request.POST.get('table_name'),
        )
        if table_name_error:
            messages.error(request, table_name_error)
            return redirect('structures:type_manage', type_code=type_code)

        result = SQLExecutor.create_table(structure_type)
        if result['success']:
            messages.success(request, f'Таблица {structure_type.table_name} создана в БД.')
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
        return redirect('structures:type_manage', type_code=type_code)

    def get(self, request, type_code):
        return HttpResponseNotAllowed(['POST'])


class StructureTypeDropTableView(View):
    template_name = 'structures/type_drop_table_confirm.html'

    def get_structure_type(self, type_code):
        return get_object_or_404(
            StructureType.objects.prefetch_related('fields'),
            code=type_code,
            is_active=True,
        )

    def get(self, request, type_code):
        structure_type = self.get_structure_type(type_code)
        if not structure_type.is_created:
            messages.warning(request, 'SQL-таблица ещё не создана.')
            return redirect('structures:type_manage', type_code=type_code)

        return render(
            request,
            self.template_name,
            {
                'structure_type': structure_type,
                'linked_materials_count': Material.objects.filter(
                    struct_type=structure_type,
                ).count(),
            },
        )

    def post(self, request, type_code):
        structure_type = self.get_structure_type(type_code)
        if not structure_type.is_created:
            messages.warning(request, 'SQL-таблица ещё не создана.')
            return redirect('structures:type_manage', type_code=type_code)

        result = SQLExecutor.drop_table(structure_type)
        if result['success']:
            messages.success(request, f'Таблица {structure_type.table_name} удалена из БД.')
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
        return redirect('structures:type_manage', type_code=type_code)
