from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.samples.forms import SampleAttachmentForm, SampleForm
from apps.samples.models import Sample, SampleAttachment


class SampleListView(ListView):
    model = Sample
    template_name = 'samples/list.html'
    context_object_name = 'samples'
    paginate_by = 10

    def get_queryset(self):
        return Sample.objects.select_related('material').all()


class SampleDetailView(DetailView):
    model = Sample
    template_name = 'samples/detail.html'
    context_object_name = 'sample'
    active_tab = 'sample'

    def get_queryset(self):
        return Sample.objects.select_related('material')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = self.active_tab
        context['scan_count'] = self.object.scans.count()
        context['attachment_count'] = self.object.attachments.count()
        context['scans'] = self.object.scans.all()[:5]
        context['attachments'] = self.object.attachments.all()[:5]
        return context


class SampleCreateView(CreateView):
    model = Sample
    form_class = SampleForm
    template_name = 'samples/form.html'

    def get_initial(self):
        initial = super().get_initial()
        material_id = self.request.GET.get('material')
        if material_id:
            initial['material'] = material_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Образец создан.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('samples:detail', kwargs={'pk': self.object.pk})


class SampleUpdateView(UpdateView):
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

    def form_valid(self, form):
        messages.success(self.request, 'Образец сохранён.')
        return super().form_valid(form)

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


class AttachmentListView(SampleAttachmentMixin, ListView):
    model = SampleAttachment
    template_name = 'samples/attachments/list.html'
    context_object_name = 'attachments'

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
        return self.sample.attachments.all()


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
