from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.creator import assign_creator
from apps.core.file_download import build_file_download_response

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    SCAN_METHOD_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    UPLOADED_BY_CREATOR_FILTER,
    QuerySetFilterMixin,
    build_choice_label_filter,
)
from apps.samples.models import Sample
from apps.scans.forms import ScanRecordForm
from apps.scans.models import ScanRecord
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import samples_in_workspace, samples_visible_in, scans_in_workspace, scans_visible_in


class ScanMethodFilterMixin:
    def get_custom_search_scope_filters(self):
        return {
            SCAN_METHOD_SEARCH_SCOPE: build_choice_label_filter(
                ScanRecord.METHODS,
                'method',
            ),
            CREATOR_SEARCH_SCOPE: UPLOADED_BY_CREATOR_FILTER,
        }


class AllScansListView(AppViewMixin, ScanMethodFilterMixin, QuerySetFilterMixin, ListView):
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
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', (
            'title',
            'description',
            'sample__code',
            'sample__name',
            'sample__material__code',
            'sample__material__name',
        )),
        ('title', 'Название', ('title',)),
        ('sample', 'Образец', ('sample__code', 'sample__name')),
        ('material', 'Материал', ('sample__material__code', 'sample__material__name')),
        ('description', 'Описание', ('description',)),
        (SCAN_METHOD_SEARCH_SCOPE, 'Метод', ()),
        (CREATOR_SEARCH_SCOPE, 'Загрузил', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('method', 'method'),)
    choice_filter_labels = {'method': 'Метод'}

    def get_queryset(self):
        return self.filter_queryset(
            scans_visible_in(self.request.active_workspace)
            .select_related(
                'sample', 'sample__material', 'sample__material__struct_type', 'uploaded_by_user'
            )
            .prefetch_related('tags')
        )

    def get_choice_filter_options(self):
        return {'method': ScanRecord.METHODS}


class SampleScanMixin:
    active_tab = 'scans'

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


class ScanListView(AppViewMixin, ScanMethodFilterMixin, QuerySetFilterMixin, SampleScanMixin, ListView):
    model = ScanRecord
    template_name = 'scans/list.html'
    context_object_name = 'scans'
    enable_tag_filter = True
    search_fields = ('title', 'description', 'file')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('title', 'description', 'file')),
        ('title', 'Название', ('title',)),
        ('description', 'Описание', ('description',)),
        ('file', 'Файл', ('file',)),
        (SCAN_METHOD_SEARCH_SCOPE, 'Метод', ()),
        (CREATOR_SEARCH_SCOPE, 'Загрузил', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('method', 'method'),)
    choice_filter_labels = {'method': 'Метод'}

    def get_choice_filter_options(self):
        return {'method': ScanRecord.METHODS}

    def get_scan_form(self):
        if hasattr(self, '_scan_form'):
            return self._scan_form
        kwargs = {'prefix': 'scan', 'sample': self.sample}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
            kwargs['files'] = self.request.FILES
        return ScanRecordForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = ScanRecordForm(
            request.POST,
            request.FILES,
            prefix='scan',
            sample=self.sample,
        )
        if form.is_valid():
            scan = form.save(commit=False)
            scan.sample = self.sample
            scan.workspace = self.sample.workspace
            assign_creator(scan, request.user)
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


class ScanDetailView(AppViewMixin, SampleScanMixin, DetailView):
    model = ScanRecord
    template_name = 'scans/detail.html'
    context_object_name = 'scan'

    def get_queryset(self):
        return self.sample.scans.prefetch_related('tags')


class ScanCreateView(AppViewMixin, SampleScanMixin, CreateView):
    model = ScanRecord
    form_class = ScanRecordForm
    template_name = 'scans/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['sample'] = self.sample
        kwargs['workspace'] = self.request.active_workspace
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        form.instance.sample = self.sample
        form.instance.workspace = self.sample.workspace
        assign_creator(form.instance, self.request.user)
        messages.success(self.request, 'Скан успешно загружен.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': self.object.pk})


class ScanUpdateView(AppViewMixin, SampleScanMixin, UpdateView):
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


class ScanDeleteView(AppViewMixin, SampleScanMixin, DeleteView):
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


class ScanDownloadView(AppViewMixin, SampleScanMixin, View):
    def get(self, request, *args, **kwargs):
        scan = get_object_or_404(self.sample.scans.all(), pk=kwargs['pk'])
        if not scan.file:
            raise Http404('Файл не найден')
        return build_file_download_response(scan.file, filename=scan.filename)
