from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import CreateView, TemplateView, UpdateView, View

from apps.materials.models import Material
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.type_forms import StructureFieldInlineFormSet, StructureTypeForm


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
        return context

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

        messages.success(self.request, 'Тип структуры создан. Создайте SQL-таблицу, когда поля будут готовы.')
        return redirect('structures:type_manage', type_code=self.object.code)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        structure_type = self.get_structure_type()
        context['structure_type'] = structure_type
        context['fields'] = structure_type.fields.all()
        context['can_create_table'] = (
            not structure_type.is_created and structure_type.fields.exists()
        )
        context['can_drop_table'] = structure_type.is_created
        context['linked_materials_count'] = Material.objects.filter(
            struct_type=structure_type,
        ).count()
        context['table_exists'] = (
            structure_type.is_created or SQLExecutor.table_exists(structure_type)
        )
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

        if not structure_type.fields.exists():
            messages.error(request, 'Добавьте хотя бы одно поле перед созданием таблицы.')
            return redirect('structures:type_edit', type_code=type_code)

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
