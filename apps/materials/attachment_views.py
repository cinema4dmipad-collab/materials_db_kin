from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import DeleteView, ListView

from apps.core.list_filters import QuerySetFilterMixin
from apps.materials.forms_attachments import MaterialAttachmentForm
from apps.materials.models import MaterialAttachment
from apps.materials.tab_mixins import MaterialTabMixin


class MaterialAttachmentMixin(MaterialTabMixin):
    active_tab = 'attachments'


class MaterialAttachmentListView(QuerySetFilterMixin, MaterialAttachmentMixin, ListView):
    model = MaterialAttachment
    template_name = 'materials/attachments/list.html'
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
        return MaterialAttachmentForm(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = MaterialAttachmentForm(request.POST, request.FILES, prefix='attachment')
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.material = self.material
            attachment.save()
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
        return self.filter_queryset(self.material.attachments.all())


class MaterialAttachmentDeleteView(MaterialAttachmentMixin, DeleteView):
    model = MaterialAttachment
    template_name = 'materials/attachments/confirm_delete.html'
    context_object_name = 'attachment'

    def get_queryset(self):
        return self.material.attachments.all()

    def get_success_url(self):
        return reverse('material_attachments:list', material_pk=self.material.pk)

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, 'Файл удалён.')
        return redirect(self.get_success_url())
