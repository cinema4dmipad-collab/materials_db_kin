from django.contrib import messages
from django.core.exceptions import PermissionDenied
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
from apps.scans.forms import ScanRecordForm, ScanTagsForm
from apps.scans.models import ScanRecord
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import samples_in_workspace, samples_visible_in, scans_in_workspace, scans_visible_in


def scan_is_editable_in_workspace(scan, workspace) -> bool:
    if scan is None or workspace is None:
        return False
    return scan.workspace_id == workspace.pk


def scan_tag_workspace(*, sample=None, scan=None, fallback=None):
    """Workspace for tag assignment — entity home, not the viewer's active workspace."""
    if scan is not None and getattr(scan, 'workspace_id', None):
        return scan.workspace
    if sample is not None and getattr(sample, 'workspace_id', None):
        return sample.workspace
    return fallback


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
        kwargs = {
            'prefix': 'scan',
            'sample': self.sample,
            'workspace': scan_tag_workspace(
                sample=self.sample,
                fallback=self.request.active_workspace,
            ),
        }
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
            workspace=scan_tag_workspace(
                sample=self.sample,
                fallback=request.active_workspace,
            ),
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_ws = self.request.active_workspace
        context['scan_is_editable'] = scan_is_editable_in_workspace(self.object, active_ws)
        context['scan_active_tab'] = 'detail'
        context['scan_attachment_count'] = self.object.attachments.count()
        tag_ws = scan_tag_workspace(
            scan=self.object,
            sample=self.sample,
            fallback=active_ws,
        )
        # Explicit id for keenetix:// deep link (scan/sample workspace may be null).
        context['keenetix_workspace_id'] = getattr(tag_ws, 'pk', None) or getattr(
            active_ws, 'pk', None
        )
        if context['scan_is_editable']:
            context['tags_form'] = ScanTagsForm(
                instance=self.object,
                workspace=tag_ws,
            )
        from apps.core.bookmarks import bookmark_context
        from apps.core.models import BookmarkEntityType

        context.update(
            bookmark_context(
                self.request,
                entity_type=BookmarkEntityType.SCAN,
                entity=self.object,
                parent_id=self.sample.pk,
            )
        )
        return context


class ScanTagsUpdateView(AppViewMixin, SampleScanMixin, UpdateView):
    """Сохранение тегов с карточки скана без полной формы редактирования."""

    model = ScanRecord
    form_class = ScanTagsForm
    http_method_names = ['post']
    context_object_name = 'scan'

    def get_queryset(self):
        return self.sample.scans.all()

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not scan_is_editable_in_workspace(obj, self.request.active_workspace):
            raise PermissionDenied
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = scan_tag_workspace(
            scan=self.object,
            sample=self.sample,
            fallback=self.request.active_workspace,
        )
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Теги скана сохранены.')
        return redirect('scans:detail', sample_pk=self.sample.pk, pk=self.object.pk)

    def form_invalid(self, form):
        for error in form.errors.get('tag_names', form.non_field_errors()):
            messages.error(self.request, error)
        return redirect('scans:detail', sample_pk=self.sample.pk, pk=self.object.pk)


class ScanCreateView(AppViewMixin, SampleScanMixin, CreateView):
    model = ScanRecord
    form_class = ScanRecordForm
    template_name = 'scans/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['sample'] = self.sample
        kwargs['workspace'] = scan_tag_workspace(
            sample=self.sample,
            fallback=self.request.active_workspace,
        )
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['sample'] = self.sample
        kwargs['workspace'] = scan_tag_workspace(
            scan=self.object,
            sample=self.sample,
            fallback=self.request.active_workspace,
        )
        return kwargs

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


class ScanPreviewView(AppViewMixin, SampleScanMixin, View):
    """Stream preview image through the app (S3/SeaweedFS may be unreachable from browser)."""

    def get(self, request, *args, **kwargs):
        scan = get_object_or_404(self.sample.scans.all(), pk=kwargs['pk'])
        if not scan.preview:
            raise Http404('Превью не найдено')
        filename = scan.preview.name.rsplit('/', 1)[-1]
        return build_file_download_response(
            scan.preview,
            filename=filename,
            as_attachment=False,
        )
