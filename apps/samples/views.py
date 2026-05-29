from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.list_filters import QuerySetFilterMixin
from apps.samples.forms import SampleAttachmentForm, SampleForm, SamplePropertyFormSet
from apps.samples.models import Sample, SampleAttachment


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
        if 'formset' not in context:
            context['formset'] = self.get_formset()
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
    search_placeholder = 'Код, название, материал или тег...'
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта', 'tag': 'Тег'}

    def get_queryset(self):
        return self.filter_queryset(
            Sample.objects.select_related('material').prefetch_related('tags')
        )

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}


class SampleDetailView(DetailView):
    model = Sample
    template_name = 'samples/detail.html'
    context_object_name = 'sample'
    active_tab = 'sample'

    def get_queryset(self):
        return Sample.objects.select_related('material').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = self.active_tab
        context['scan_count'] = self.object.scans.count()
        context['attachment_count'] = self.object.attachments.count()
        context['scans'] = self.object.scans.all()[:5]
        context['attachments'] = self.object.attachments.all()[:5]
        context['properties'] = (
            self.object.properties.select_related('property', 'property__group').order_by(
                'property__group__sort_order',
                'property__name',
            )
        )
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
    search_placeholder = 'Название, описание или имя файла...'

    def get_attachment_form(self):
        if hasattr(self, '_attachment_form'):
            return self._attachment_form
        kwargs = {'prefix': 'attachment'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
            kwargs['files'] = self.request.FILES
        return SampleAttachmentForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = SampleAttachmentForm(request.POST, request.FILES, prefix='attachment')
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
