from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    DEFAULT_CREATOR_FILTER,
    QuerySetFilterMixin,
)
from apps.core.creator import assign_creator
from apps.references.forms import PropertyChoiceInlineFormSet, PropertyForm
from apps.references.models import Property, PropertyChoice, PropertyGroup
from apps.workspaces.mixins import AppViewMixin, PermissionRequiredMixin, SystemAdminRequiredMixin
from apps.workspaces.permissions import WorkspacePerm


class PropertyChoiceFormMixin:
    def get_choice_formset(self):
        instance = getattr(self, 'object', None) or Property()
        kwargs = {'prefix': 'choices', 'instance': instance}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        return PropertyChoiceInlineFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'choice_formset' not in context:
            context['choice_formset'] = self.get_choice_formset()
        return context

    def _save_with_choices(self, form):
        is_choice = form.cleaned_data.get('data_type') == Property.CHOICE_DATA_TYPE
        choice_formset = None
        if is_choice:
            choice_formset = self.get_choice_formset()
            choice_formset.property_form = form
            if not choice_formset.is_valid():
                return None, choice_formset

        with transaction.atomic():
            self.object = form.save()
            if is_choice:
                choice_formset.instance = self.object
                choice_formset.save()
            elif self.object.pk:
                self.object.choices.all().delete()
        return self.object, choice_formset


class PropertyListView(AppViewMixin, PermissionRequiredMixin, QuerySetFilterMixin, ListView):
    permission_codename = WorkspacePerm.PROPERTY_VIEW
    model = Property
    template_name = 'references/property_list.html'
    context_object_name = 'properties'
    paginate_by = 20
    search_fields = ('name', 'display_name', 'unit', 'description')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('name', 'display_name', 'unit', 'description')),
        ('name', 'Имя', ('name',)),
        ('display_name', 'Название', ('display_name',)),
        ('unit', 'Единица', ('unit',)),
        ('description', 'Описание', ('description',)),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('group', 'group_id'), ('data_type', 'data_type'))
    choice_filter_labels = {'group': 'Группа', 'data_type': 'Тип данных'}

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: DEFAULT_CREATOR_FILTER,
        }

    def get_queryset(self):
        return self.filter_queryset(
            Property.objects.select_related('group', 'created_by_user')
            .annotate(material_count=Count('material_values'))
            .order_by('group__sort_order', 'display_name', 'name')
        )

    def get_choice_filter_options(self):
        return {
            'group': list(
                PropertyGroup.objects.order_by('sort_order', 'name').values_list('pk', 'name')
            ),
            'data_type': Property.DATA_TYPES,
        }


class PropertyCreateView(PropertyChoiceFormMixin, SystemAdminRequiredMixin, AppViewMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'references/property_form.html'
    success_url = reverse_lazy('references:list')

    def _safe_next_url(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
        ):
            return next_url
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        next_url = self._safe_next_url()
        context['next_url'] = next_url or ''
        context['cancel_url'] = next_url or reverse_lazy('references:list')
        return context

    def get_success_url(self):
        next_url = self._safe_next_url()
        if next_url:
            separator = '&' if '?' in next_url else '?'
            created_property = self.object.pk
            return (
                f'{next_url}{separator}created_property={created_property}'
                f'&open_properties=1'
            )
        return str(self.success_url)

    def form_valid(self, form):
        assign_creator(form.instance, self.request.user)
        saved, choice_formset = self._save_with_choices(form)
        if saved is None:
            return self.render_to_response(
                self.get_context_data(form=form, choice_formset=choice_formset)
            )
        messages.success(self.request, f'Свойство «{self.object.display_name}» создано.')
        return HttpResponseRedirect(self.get_success_url())


class PropertyUpdateView(PropertyChoiceFormMixin, SystemAdminRequiredMixin, AppViewMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'references/property_form.html'
    context_object_name = 'property_obj'

    def get_queryset(self):
        return Property.objects.prefetch_related(
            Prefetch('choices', queryset=PropertyChoice.objects.order_by('sort_order', 'label'))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('references:list')
        return context

    def form_valid(self, form):
        saved, choice_formset = self._save_with_choices(form)
        if saved is None:
            return self.render_to_response(
                self.get_context_data(form=form, choice_formset=choice_formset)
            )
        messages.success(self.request, f'Свойство «{self.object.display_name}» сохранено.')
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('references:list')


class PropertyDeleteView(SystemAdminRequiredMixin, AppViewMixin, DeleteView):
    model = Property
    template_name = 'references/property_confirm_delete.html'
    context_object_name = 'property_obj'
    success_url = reverse_lazy('references:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['material_count'] = self.object.material_values.count()
        return context

    def form_valid(self, form):
        display_name = self.object.display_name
        response = super().form_valid(form)
        messages.success(self.request, f'Свойство «{display_name}» удалено.')
        return response
