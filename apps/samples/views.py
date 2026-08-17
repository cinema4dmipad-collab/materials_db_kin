from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.attachments.processing import schedule_attachment_preview
from apps.core.bulk import parse_bulk_ids
from apps.core.creator import assign_creator
from apps.core.file_download import build_file_download_response

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    CREATOR_WITH_LABEL_FILTER,
    OBJECT_TYPE_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    UPLOADED_BY_CREATOR_FILTER,
    QuerySetFilterMixin,
    build_choice_label_filter,
)
from apps.core.table_sort import TableSortMixin
from apps.materials.models import Material
from apps.materials.structure_display import get_sample_structure_context
from apps.core.property_form_display import enrich_property_form_display
from apps.samples.forms import (
    SampleAttachmentForm,
    SampleForm,
    SamplePropertyForm,
    SamplePropertyFormSet,
    SamplePropertyInlineFormSet,
    SampleTagsForm,
)
from apps.samples.models import Sample, SampleAttachment, SampleProperty
from apps.materials.picker_data import materials_for_picker
from apps.structures.property_mapping import reference_properties_for_picker
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import materials_visible_in, samples_in_workspace, samples_visible_in


def sample_is_editable_in_workspace(sample, workspace) -> bool:
    if sample is None or workspace is None:
        return False
    return sample.workspace_id == workspace.pk


def warn_extra_sample_properties(request, sample):
    material_property_ids = set(
        sample.material.properties.values_list('property_id', flat=True)
    )
    extra_properties = list(
        sample.properties.select_related('property').exclude(
            property_id__in=material_property_ids
        )
    )
    if not extra_properties:
        return

    labels = [item.property.display_name for item in extra_properties]
    messages.warning(
        request,
        'Следующие свойства образца отсутствуют у материала '
        f'{sample.material.code}: {", ".join(labels)}.',
    )


def _resolve_sample_material(form=None, sample=None, request=None):
    if sample is not None and getattr(sample, 'material_id', None):
        return sample.material
    if form is not None:
        material_id = None
        if form.is_bound:
            material_id = form.data.get('material') or form['material'].value()
        else:
            material_id = form.initial.get('material') or form['material'].value()
        if material_id:
            return Material.objects.filter(pk=material_id).first()
    if request is not None:
        material_id = request.GET.get('material')
        if material_id:
            return Material.objects.filter(pk=material_id).first()
    return None


def _material_property_ids(material):
    if material is None:
        return set()
    return set(material.properties.values_list('property_id', flat=True))


def _form_property_id(form):
    from apps.core.property_form_display import form_property_id

    return form_property_id(form)


def _split_sample_property_formset(formset, material_property_ids):
    material_id_strs = {str(item) for item in material_property_ids}
    material_forms = []
    extra_forms = []
    for form in formset:
        prop_id = _form_property_id(form)
        if prop_id and prop_id in material_id_strs:
            material_forms.append(form)
        else:
            extra_forms.append(form)
    return material_forms, extra_forms


def _material_property_formset_initial(material):
    if material is None:
        return []
    return [
        {
            'property': item.property,
            'value_kind': item.value_kind,
            'value': item.value,
            'value_b': item.value_b,
        }
        for item in material.properties.select_related('property').order_by(
            'property__group__sort_order',
            'property__name',
        )
    ]


def _build_sample_property_formset_from_material(*, material, instance=None):
    from django.forms import inlineformset_factory

    initial = _material_property_formset_initial(material)
    formset_class = inlineformset_factory(
        Sample,
        SampleProperty,
        form=SamplePropertyForm,
        fields=['property', 'value_kind', 'value', 'value_b'],
        extra=len(initial),
        can_delete=True,
        formset=SamplePropertyInlineFormSet,
    )
    return formset_class(
        prefix='properties',
        initial=initial,
        queryset=SampleProperty.objects.none(),
        instance=instance or Sample(),
    )


class SampleFormsetMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        instance = getattr(self, 'object', None)
        if instance is not None and getattr(instance, 'workspace_id', None):
            kwargs['workspace'] = instance.workspace
        else:
            kwargs['workspace'] = self.request.active_workspace
        return kwargs

    def get_formset(self):
        kwargs = {'prefix': 'properties'}
        if self.request.method == 'POST' and not self.request.POST.get('_apply_material'):
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        return SamplePropertyFormSet(**kwargs)

    def post(self, request, *args, **kwargs):
        if request.POST.get('_apply_material'):
            if isinstance(self, UpdateView):
                self.object = self.get_object()
            else:
                self.object = None
            return self.render_apply_material()
        return super().post(request, *args, **kwargs)

    def render_apply_material(self):
        instance = getattr(self, 'object', None)
        form = SampleForm(
            self.request.POST,
            instance=instance,
            skip_validation=True,
            workspace=self.get_form_kwargs()['workspace'],
        )
        material = _resolve_sample_material(form=form, sample=instance, request=self.request)
        formset = _build_sample_property_formset_from_material(
            material=material,
            instance=instance,
        )
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        formset = context.get('formset')
        if formset is None:
            formset = self.get_formset()
            context['formset'] = formset

        form = context.get('form')
        sample = context.get('sample') or getattr(self, 'object', None)
        material = _resolve_sample_material(form=form, sample=sample, request=self.request)
        material_property_ids = _material_property_ids(material)
        material_forms, extra_forms = _split_sample_property_formset(
            formset,
            material_property_ids,
        )
        for property_form in material_forms + extra_forms:
            enrich_property_form_display(property_form)

        context['material_property_forms'] = material_forms
        context['extra_property_forms'] = extra_forms
        context['material_property_ids'] = [str(item) for item in material_property_ids]
        context['reference_materials'] = materials_for_picker(self.request.active_workspace)
        context['reference_properties'] = reference_properties_for_picker()
        return context

    def form_valid(self, form):
        is_update = isinstance(self, UpdateView)
        original_pk = self.object.pk if is_update else None
        formset = None
        saved = False

        try:
            with transaction.atomic():
                if not is_update:
                    form.instance.workspace = self.request.active_workspace
                    assign_creator(form.instance, self.request.user)
                self.object = form.save()
                formset = SamplePropertyFormSet(
                    self.request.POST,
                    instance=self.object,
                    prefix='properties',
                )
                if not formset.is_valid():
                    transaction.set_rollback(True)
                else:
                    formset.save()
                    saved = True
        except forms.ValidationError as exc:
            form.add_error(None, exc)

        if saved:
            warn_extra_sample_properties(self.request, self.object)
            messages.success(
                self.request,
                'Образец сохранён.' if is_update else 'Образец создан.',
            )
            return HttpResponseRedirect(self.get_success_url())

        if is_update and original_pk:
            self.object = Sample.objects.get(pk=original_pk)
        elif not is_update:
            self.object = None

        if formset is not None and not formset.is_valid():
            messages.error(self.request, 'Проверьте значения свойств образца.')

        return self.render_to_response(
            self.get_context_data(
                form=form,
                formset=formset or self.get_formset(),
            )
        )


class SampleListView(AppViewMixin, QuerySetFilterMixin, TableSortMixin, ListView):
    model = Sample
    template_name = 'samples/list.html'
    context_object_name = 'samples'
    paginate_by = 10
    enable_tag_filter = True
    sort_columns = (
        ('code', 'code'),
        ('name', 'name'),
        ('material', 'material__code'),
        ('created_at', 'created_at'),
    )
    search_fields = ('code', 'name', 'description', 'material__code', 'material__name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('code', 'name', 'description', 'material__code', 'material__name')),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        ('description', 'Описание', ('description',)),
        ('material', 'Материал', ('material__code', 'material__name')),
        (OBJECT_TYPE_SEARCH_SCOPE, 'Тип объекта', ()),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта'}

    def get_queryset(self):
        return self.apply_table_sort(
            self.filter_queryset(
                samples_visible_in(self.request.active_workspace)
                .select_related('material', 'material__struct_type', 'created_by_user')
                .prefetch_related('tags')
            )
        )

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}

    def get_custom_search_scope_filters(self):
        return {
            OBJECT_TYPE_SEARCH_SCOPE: build_choice_label_filter(
                Sample.OBJECT_TYPES,
                'object_type',
            ),
            CREATOR_SEARCH_SCOPE: CREATOR_WITH_LABEL_FILTER,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_table_sort_context())
        return context


class SampleDetailView(AppViewMixin, DetailView):
    model = Sample
    template_name = 'samples/detail.html'
    context_object_name = 'sample'
    active_tab = 'sample'

    def get_queryset(self):
        return (
            samples_visible_in(self.request.active_workspace)
            .select_related(
                'material',
                'material__struct_type',
                'struct_type',
                'created_by_user',
            )
            .prefetch_related('tags')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_ws = self.request.active_workspace
        context['active_tab'] = self.active_tab
        context['sample_is_editable'] = sample_is_editable_in_workspace(self.object, active_ws)
        if context['sample_is_editable']:
            context['tags_form'] = SampleTagsForm(
                instance=self.object,
                workspace=self.object.workspace or active_ws,
            )
        context['scan_count'] = self.object.scans.count()
        context['attachment_count'] = self.object.attachments.count()
        context['scans'] = self.object.scans.all()[:5]
        context['attachments'] = self.object.attachments.all()[:5]
        material_property_ids = set(
            self.object.material.properties.values_list('property_id', flat=True)
        )
        sample_properties = list(
            self.object.properties.select_related('property', 'property__group').order_by(
                'property__group__sort_order',
                'property__name',
            )
        )
        context['material_properties'] = [
            item for item in sample_properties if item.property_id in material_property_ids
        ]
        context['extra_properties'] = [
            item for item in sample_properties if item.property_id not in material_property_ids
        ]
        context.update(get_sample_structure_context(self.object))
        from apps.core.bookmarks import bookmark_context
        from apps.core.models import BookmarkEntityType

        context.update(
            bookmark_context(
                self.request,
                entity_type=BookmarkEntityType.SAMPLE,
                entity=self.object,
            )
        )
        return context


class SampleTagsUpdateView(AppViewMixin, UpdateView):
    """Сохранение тегов с карточки образца без полной формы редактирования."""

    model = Sample
    form_class = SampleTagsForm
    http_method_names = ['post']
    context_object_name = 'sample'

    def get_queryset(self):
        return samples_visible_in(self.request.active_workspace)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not sample_is_editable_in_workspace(obj, self.request.active_workspace):
            raise PermissionDenied
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.object.workspace or self.request.active_workspace
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Теги образца сохранены.')
        return redirect('samples:detail', pk=self.object.pk)

    def form_invalid(self, form):
        for error in form.errors.get('tag_names', form.non_field_errors()):
            messages.error(self.request, error)
        return redirect('samples:detail', pk=self.object.pk)


class SampleCreateView(AppViewMixin, SampleFormsetMixin, CreateView):
    model = Sample
    form_class = SampleForm
    template_name = 'samples/form.html'

    def get_initial(self):
        initial = super().get_initial()
        material_id = self.request.GET.get('material')
        if material_id:
            from apps.materials.picker_data import materials_for_picker_queryset

            if materials_for_picker_queryset(
                self.request.active_workspace,
            ).filter(pk=material_id).exists():
                initial['material'] = material_id
        return initial

    def get_success_url(self):
        return reverse('samples:detail', kwargs={'pk': self.object.pk})


class SampleUpdateView(AppViewMixin, SampleFormsetMixin, UpdateView):
    model = Sample
    form_class = SampleForm
    template_name = 'samples/form.html'
    context_object_name = 'sample'
    active_tab = 'sample'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = self.active_tab
        context['scan_count'] = self.object.scans.count()
        context['attachment_count'] = self.object.attachments.count()
        return context

    def get_success_url(self):
        return reverse('samples:detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        return samples_in_workspace(self.request.active_workspace)


class SampleDeleteView(AppViewMixin, DeleteView):
    model = Sample
    template_name = 'samples/confirm_delete.html'
    context_object_name = 'sample'
    success_url = reverse_lazy('samples:list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Образец удалён.')
        return super().delete(request, *args, **kwargs)


    def get_queryset(self):
        return samples_in_workspace(self.request.active_workspace)


class SampleBulkDeleteView(AppViewMixin, View):
    template_name = 'includes/bulk_confirm_delete.html'
    max_items = 100

    def get(self, request, *args, **kwargs):
        return redirect('samples:list')

    def post(self, request, *args, **kwargs):
        ids = parse_bulk_ids(request, max_items=self.max_items)
        if not ids:
            messages.warning(request, 'Не выбрано ни одного образца.')
            return redirect('samples:list')

        workspace = request.active_workspace
        samples = list(
            samples_in_workspace(workspace).filter(pk__in=ids).select_related('material')
        )
        by_pk = {str(s.pk): s for s in samples}
        deletable = [by_pk[i] for i in ids if i in by_pk]

        if request.POST.get('confirm') != '1':
            return TemplateResponse(
                request,
                self.template_name,
                {
                    'page_title': 'Удаление выбранных образцов',
                    'warning_text': (
                        f'Будут удалены <strong>{len(deletable)}</strong> образец(ов) '
                        'вместе со сканами и вложениями.'
                    ),
                    'deletable': [
                        {'label': s.name, 'code': s.code} for s in deletable
                    ],
                    'blocked': [],
                    'ids': [str(s.pk) for s in deletable],
                    'cancel_url': reverse('samples:list'),
                },
            )

        if not deletable:
            messages.warning(request, 'Нет образцов для удаления.')
            return redirect('samples:list')

        deleted = 0
        for sample in deletable:
            sample.delete()
            deleted += 1
        messages.success(request, f'Удалено образцов: {deleted}.')
        return redirect('samples:list')


class SampleAttachmentMixin:
    active_tab = 'attachments'

    def dispatch(self, request, *args, **kwargs):
        self.sample = get_object_or_404(
            samples_visible_in(request.active_workspace).select_related('material'),
            pk=kwargs['sample_pk'],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sample'] = self.sample
        context['active_tab'] = self.active_tab
        context['scan_count'] = self.sample.scans.count()
        context['attachment_count'] = self.sample.attachments.count()
        return context


class AttachmentListView(AppViewMixin, QuerySetFilterMixin, SampleAttachmentMixin, ListView):
    model = SampleAttachment
    template_name = 'samples/attachments/list.html'
    context_object_name = 'attachments'
    search_fields = ('title', 'description', 'file')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('title', 'description', 'file')),
        ('title', 'Название', ('title',)),
        ('description', 'Описание', ('description',)),
        ('file', 'Файл', ('file',)),
        (CREATOR_SEARCH_SCOPE, 'Загрузил', ()),
    )
    search_placeholder = 'Введите текст для поиска...'

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: UPLOADED_BY_CREATOR_FILTER,
        }

    def get_queryset(self):
        return self.filter_queryset(self.sample.attachments.all())


class AttachmentCreateView(AppViewMixin, SampleAttachmentMixin, CreateView):
    model = SampleAttachment
    form_class = SampleAttachmentForm
    template_name = 'samples/attachments/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['prefix'] = 'attachment'
        kwargs['sample'] = self.sample
        return kwargs

    def form_valid(self, form):
        attachment = form.save(commit=False)
        attachment.sample = self.sample
        assign_creator(attachment, self.request.user)
        attachment.save()
        schedule_attachment_preview(attachment)
        messages.success(self.request, 'Файл прикреплён к образцу.')
        return redirect('attachments:list', sample_pk=self.sample.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attachment_form'] = context['form']
        context['cancel_url'] = reverse('attachments:list', kwargs={'sample_pk': self.sample.pk})
        return context


class AttachmentDeleteView(AppViewMixin, SampleAttachmentMixin, DeleteView):
    model = SampleAttachment
    template_name = 'samples/attachments/confirm_delete.html'
    context_object_name = 'attachment'

    def get_queryset(self):
        return self.sample.attachments.all()

    def get_success_url(self):
        return reverse('attachments:list', kwargs={'sample_pk': self.sample.pk})

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, 'Файл удалён.')
        return redirect(self.get_success_url())


class AttachmentDownloadView(AppViewMixin, SampleAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(self.sample.attachments.all(), pk=kwargs['pk'])
        if not attachment.file:
            raise Http404('Файл не найден')
        return build_file_download_response(attachment.file, filename=attachment.filename)


class AttachmentPreviewView(AppViewMixin, SampleAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(self.sample.attachments.all(), pk=kwargs['pk'])
        if not attachment.preview_image:
            raise Http404('Превью не найдено')
        filename = attachment.preview_image.name.rsplit('/', 1)[-1]
        return build_file_download_response(
            attachment.preview_image,
            filename=filename,
            as_attachment=False,
        )
