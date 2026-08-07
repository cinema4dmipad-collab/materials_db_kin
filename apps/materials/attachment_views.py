from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DeleteView, ListView

from apps.core.attachments.processing import schedule_attachment_preview
from apps.core.file_download import build_file_download_response

from apps.core.creator import assign_creator
from apps.core.list_filters import ALL_SEARCH_SCOPE, CREATOR_SEARCH_SCOPE, UPLOADED_BY_CREATOR_FILTER, QuerySetFilterMixin
from apps.materials.forms_attachments import MaterialAttachmentForm
from apps.materials.models import MaterialAttachment
from apps.materials.services import material_attachments_for_material
from apps.materials.tab_mixins import MaterialTabMixin
from apps.workspaces.mixins import AppViewMixin


class MaterialAttachmentMixin(MaterialTabMixin):
    active_tab = 'attachments'


class MaterialAttachmentListView(AppViewMixin, QuerySetFilterMixin, MaterialAttachmentMixin, ListView):
    model = MaterialAttachment
    template_name = 'materials/attachments/list.html'
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

    def get_attachment_form(self):
        if hasattr(self, '_attachment_form'):
            return self._attachment_form
        kwargs = {'prefix': 'attachment', 'material': self.material}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
            kwargs['files'] = self.request.FILES
        return MaterialAttachmentForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self._require_material_editable()
        self.object_list = self.get_queryset()
        form = MaterialAttachmentForm(
            request.POST,
            request.FILES,
            prefix='attachment',
            material=self.material,
        )
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.material = self.material
            attachment.workspace = request.active_workspace
            assign_creator(attachment, request.user)
            attachment.save()
            schedule_attachment_preview(attachment)
            messages.success(request, 'Файл прикреплён к материалу.')
            return redirect('material_attachments:list', material_pk=self.material.pk)

        self._attachment_form = form
        context = self.get_context_data(attachments=self.object_list, attachment_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('attachment_form', self.get_attachment_form())
        return context

    def get_queryset(self):
        return self.filter_queryset(
            material_attachments_for_material(self.material, self.request.active_workspace),
        )


class MaterialAttachmentDeleteView(AppViewMixin, MaterialAttachmentMixin, DeleteView):
    model = MaterialAttachment
    template_name = 'materials/attachments/confirm_delete.html'
    context_object_name = 'attachment'

    def get_queryset(self):
        return material_attachments_for_material(self.material, self.request.active_workspace)

    def get_success_url(self):
        return reverse('material_attachments:list', material_pk=self.material.pk)

    def delete(self, request, *args, **kwargs):
        self._require_material_editable()
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, 'Файл удалён.')
        return redirect(self.get_success_url())


class MaterialAttachmentDownloadView(AppViewMixin, MaterialAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(
            material_attachments_for_material(self.material, self.request.active_workspace),
            pk=kwargs['pk'],
        )
        if not attachment.file:
            raise Http404('Файл не найден')
        return build_file_download_response(attachment.file, filename=attachment.filename)


class MaterialAttachmentPreviewView(AppViewMixin, MaterialAttachmentMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(
            material_attachments_for_material(self.material, self.request.active_workspace),
            pk=kwargs['pk'],
        )
        if not attachment.preview_image:
            raise Http404('Превью не найдено')
        filename = attachment.preview_image.name.rsplit('/', 1)[-1]
        return build_file_download_response(
            attachment.preview_image,
            filename=filename,
            as_attachment=False,
        )
