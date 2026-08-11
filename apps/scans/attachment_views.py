from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView

from apps.core.attachments.processing import schedule_attachment_preview
from apps.core.creator import assign_creator
from apps.core.file_download import build_file_download_response
from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    UPLOADED_BY_CREATOR_FILTER,
    QuerySetFilterMixin,
)
from apps.scans.forms_attachments import ScanAttachmentForm
from apps.scans.models import ScanAttachment
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import samples_visible_in, scans_visible_in


class ScanAttachmentMixin:
    active_tab = 'scan_attachments'

    def dispatch(self, request, *args, **kwargs):
        self.sample = get_object_or_404(
            samples_visible_in(request.active_workspace).select_related('material'),
            pk=kwargs['sample_pk'],
        )
        self.scan = get_object_or_404(
            scans_visible_in(request.active_workspace).filter(sample=self.sample),
            pk=kwargs['scan_pk'],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sample'] = self.sample
        context['scan'] = self.scan
        context['active_tab'] = 'scans'
        context['scan_active_tab'] = 'attachments'
        context['scan_count'] = self.sample.scans.count()
        context['attachment_count'] = self.sample.attachments.count()
        context['scan_attachment_count'] = self.scan.attachments.count()
        return context


class ScanAttachmentListView(AppViewMixin, QuerySetFilterMixin, ScanAttachmentMixin, ListView):
    model = ScanAttachment
    template_name = 'scans/attachments/list.html'
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
        return {CREATOR_SEARCH_SCOPE: UPLOADED_BY_CREATOR_FILTER}

    def get_queryset(self):
        return self.filter_queryset(self.scan.attachments.all())


class ScanAttachmentCreateView(AppViewMixin, ScanAttachmentMixin, CreateView):
    model = ScanAttachment
    form_class = ScanAttachmentForm
    template_name = 'scans/attachments/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['prefix'] = 'attachment'
        kwargs['scan'] = self.scan
        return kwargs

    def form_valid(self, form):
        attachment = form.save(commit=False)
        attachment.scan = self.scan
        attachment.workspace = self.scan.workspace or self.request.active_workspace
        assign_creator(attachment, self.request.user)
        attachment.save()
        schedule_attachment_preview(attachment)
        messages.success(self.request, 'Файл прикреплён к скану.')
        return redirect(
            'scans:attachment_list',
            sample_pk=self.sample.pk,
            scan_pk=self.scan.pk,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attachment_form'] = context['form']
        context['cancel_url'] = reverse(
            'scans:attachment_list',
            kwargs={'sample_pk': self.sample.pk, 'scan_pk': self.scan.pk},
        )
        return context


class ScanAttachmentDeleteView(AppViewMixin, ScanAttachmentMixin, DeleteView):
    model = ScanAttachment
    template_name = 'scans/attachments/confirm_delete.html'
    context_object_name = 'attachment'

    def get_queryset(self):
        return self.scan.attachments.all()

    def get_success_url(self):
        return reverse(
            'scans:attachment_list',
            kwargs={'sample_pk': self.sample.pk, 'scan_pk': self.scan.pk},
        )

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, 'Файл удалён.')
        return redirect(self.get_success_url())


class ScanAttachmentDownloadView(AppViewMixin, ScanAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(self.scan.attachments.all(), pk=kwargs['pk'])
        if not attachment.file:
            raise Http404('Файл не найден')
        return build_file_download_response(attachment.file, filename=attachment.filename)


class ScanAttachmentPreviewView(AppViewMixin, ScanAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(self.scan.attachments.all(), pk=kwargs['pk'])
        if not attachment.preview_image:
            raise Http404('Превью не найдено')
        filename = attachment.preview_image.name.rsplit('/', 1)[-1]
        return build_file_download_response(
            attachment.preview_image,
            filename=filename,
            as_attachment=False,
        )
