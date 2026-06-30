from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.file_download import build_file_download_response

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    OBJECT_TYPE_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
    build_choice_label_filter,
)
from apps.materials.models import Material
from apps.materials.structure_display import get_material_structure_context
from apps.core.property_form_display import enrich_property_form_display
from apps.samples.forms import SampleAttachmentForm, SampleForm, SamplePropertyFormSet
from apps.samples.models import Sample, SampleAttachment
from apps.materials.picker_data import materials_for_picker
from apps.structures.property_mapping import reference_properties_for_picker


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


class SampleFormsetMixin:
    def get_formset(self):
        kwargs = {'prefix': 'properties'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        return SamplePropertyFormSet(**kwargs)

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
        context['reference_materials'] = materials_for_picker()
        context['reference_properties'] = reference_properties_for_picker()
        if material:
            context.update(get_material_structure_context(material))
        else:
            context.update({
                'structure_type': None,
                'structure_properties': [],
                'structure_message': '',
            })
        return context

    def form_valid(self, form):
        is_update = isinstance(self, UpdateView)
        original_pk = self.object.pk if is_update else None
        formset = None
        saved = False

        try:
            with transaction.atomic():
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


class SampleListView(QuerySetFilterMixin, ListView):
    model = Sample
    template_name = 'samples/list.html'
    context_object_name = 'samples'
    paginate_by = 10
    enable_tag_filter = True
    search_fields = ('code', 'name', 'material__code', 'material__name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('code', 'name', 'material__code', 'material__name')),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        ('material', 'Материал', ('material__code', 'material__name')),
        (OBJECT_TYPE_SEARCH_SCOPE, 'Тип объекта', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта'}

    def get_queryset(self):
        return self.filter_queryset(
            Sample.objects.select_related('material', 'material__struct_type').prefetch_related('tags')
        )

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}

    def get_custom_search_scope_filters(self):
        return {
            OBJECT_TYPE_SEARCH_SCOPE: build_choice_label_filter(
                Sample.OBJECT_TYPES,
                'object_type',
            ),
        }


class SampleDetailView(DetailView):
    model = Sample
    template_name = 'samples/detail.html'
    context_object_name = 'sample'
    active_tab = 'sample'

    def get_queryset(self):
        return Sample.objects.select_related('material', 'material__struct_type').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = self.active_tab
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
        context.update(get_material_structure_context(self.object.material))
        return context


class SampleCreateView(SampleFormsetMixin, CreateView):
    model = Sample
    form_class = SampleForm
    template_name = 'samples/form.html'

    def get_initial(self):
        initial = super().get_initial()
        material_id = self.request.GET.get('material')
        if material_id:
            initial['material'] = material_id
        return initial

    def get_success_url(self):
        return reverse('samples:detail', kwargs={'pk': self.object.pk})


class SampleUpdateView(SampleFormsetMixin, UpdateView):
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


class SampleDeleteView(DeleteView):
    model = Sample
    template_name = 'samples/confirm_delete.html'
    context_object_name = 'sample'
    success_url = reverse_lazy('samples:list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Образец удалён.')
        return super().delete(request, *args, **kwargs)


class SampleAttachmentMixin:
    active_tab = 'attachments'

    def dispatch(self, request, *args, **kwargs):
        self.sample = get_object_or_404(Sample.objects.select_related('material'), pk=kwargs['sample_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sample'] = self.sample
        context['active_tab'] = self.active_tab
        context['scan_count'] = self.sample.scans.count()
        context['attachment_count'] = self.sample.attachments.count()
        return context


class AttachmentListView(QuerySetFilterMixin, SampleAttachmentMixin, ListView):
    model = SampleAttachment
    template_name = 'samples/attachments/list.html'
    context_object_name = 'attachments'
    search_fields = ('title', 'description', 'file')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('title', 'description', 'file')),
        ('title', 'Название', ('title',)),
        ('description', 'Описание', ('description',)),
        ('file', 'Файл', ('file',)),
    )
    search_placeholder = 'Введите текст для поиска...'

    def get_attachment_form(self):
        if hasattr(self, '_attachment_form'):
            return self._attachment_form
        kwargs = {'prefix': 'attachment', 'sample': self.sample}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
            kwargs['files'] = self.request.FILES
        return SampleAttachmentForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = SampleAttachmentForm(
            request.POST,
            request.FILES,
            prefix='attachment',
            sample=self.sample,
        )
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.sample = self.sample
            attachment.save()
            messages.success(request, 'Файл прикреплён к образцу.')
            return redirect('attachments:list', sample_pk=self.sample.pk)

        self._attachment_form = form
        context = self.get_context_data(attachments=self.object_list, attachment_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('attachment_form', self.get_attachment_form())
        return context

    def get_queryset(self):
        return self.filter_queryset(self.sample.attachments.all())


class AttachmentDeleteView(SampleAttachmentMixin, DeleteView):
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


class AttachmentDownloadView(SampleAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(self.sample.attachments.all(), pk=kwargs['pk'])
        if not attachment.file:
            raise Http404('Файл не найден')
        return build_file_download_response(attachment.file, filename=attachment.filename)
