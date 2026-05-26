from django.shortcuts import get_object_or_404

from apps.materials.models import Material


class MaterialTabMixin:
    def dispatch(self, request, *args, **kwargs):
        self.material = get_object_or_404(Material, pk=kwargs['material_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['material'] = self.material
        context['active_tab'] = self.active_tab
        context['attachment_count'] = self.material.attachments.count()
        context['sample_count'] = self.material.samples.count()
        return context
