from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.list_filters import QuerySetFilterMixin
from apps.samples.models import Sample
from apps.scans.forms import ScanRecordForm
from apps.scans.models import ScanRecord


class AllScansListView(QuerySetFilterMixin, ListView):
    model = ScanRecord
    template_name = 'scans/all_list.html'
    context_object_name = 'scans'
    paginate_by = 12
    enable_tag_filter = True
    search_fields = (
        'title',
        'description',
        'sample__code',
        'sample__name',
        'sample__material__code',
        'sample__material__name',
    )
    search_placeholder = 'Название, образец, материал или тег...'
    choice_filters = (('method', 'method'),)
    choice_filter_labels = {'method': 'Метод', 'tag': 'Тег'}

    def get_queryset(self):
        return self.filter_queryset(
            ScanRecord.objects.select_related(
                'sample', 'sample__material', 'sample__material__struct_type'
            ).prefetch_related('tags')
        )

    def get_choice_filter_options(self):
        return {'method': ScanRecord.METHODS}


class SampleScanMixin:
    active_tab = 'scans'

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


class ScanListView(QuerySetFilterMixin, SampleScanMixin, ListView):
    model = ScanRecord
    template_name = 'scans/list.html'
    context_object_name = 'scans'
    enable_tag_filter = True
    search_fields = ('title', 'description', 'file')
    search_placeholder = 'Название, описание, файл или тег...'
    choice_filters = (('method', 'method'),)
    choice_filter_labels = {'method': 'Метод', 'tag': 'Тег'}

    def get_choice_filter_options(self):
        return {'method': ScanRecord.METHODS}

    def get_scan_form(self):
        if hasattr(self, '_scan_form'):
            return self._scan_form
        kwargs = {'prefix': 'scan'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
            kwargs['files'] = self.request.FILES
        return ScanRecordForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = ScanRecordForm(request.POST, request.FILES, prefix='scan')
        if form.is_valid():
            scan = form.save(commit=False)
            scan.sample = self.sample
            scan.save()
            form.save_tags(scan)
            messages.success(request, 'Скан прикреплён к образцу.')
            return redirect('scans:list', sample_pk=self.sample.pk)

        self._scan_form = form
        context = self.get_context_data(scans=self.object_list, scan_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('scan_form', self.get_scan_form())
        return context

    def get_queryset(self):
        return self.filter_queryset(self.sample.scans.prefetch_related('tags'))


class ScanDetailView(SampleScanMixin, DetailView):
    model = ScanRecord
    template_name = 'scans/detail.html'
    context_object_name = 'scan'

    def get_queryset(self):
        return self.sample.scans.prefetch_related('tags')


class ScanCreateView(SampleScanMixin, CreateView):
    model = ScanRecord
    form_class = ScanRecordForm
    template_name = 'scans/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        form.instance.sample = self.sample
        messages.success(self.request, 'Скан успешно загружен.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': self.object.pk})


class ScanUpdateView(SampleScanMixin, UpdateView):
    model = ScanRecord
    form_class = ScanRecordForm
    template_name = 'scans/form.html'
    context_object_name = 'scan'

    def get_queryset(self):
        return self.sample.scans.prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Скан сохранён.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': self.object.pk})


class ScanDeleteView(SampleScanMixin, DeleteView):
    model = ScanRecord
    template_name = 'scans/confirm_delete.html'
    context_object_name = 'scan'

    def get_queryset(self):
        return self.sample.scans.prefetch_related('tags')

    def get_success_url(self):
        return reverse('scans:list', kwargs={'sample_pk': self.sample.pk})

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, 'Скан удалён.')
        return redirect(self.get_success_url())
