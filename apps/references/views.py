from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.core.bulk import parse_bulk_ids
from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    DEFAULT_CREATOR_FILTER,
    QuerySetFilterMixin,
)
from apps.core.creator import assign_creator
from apps.references.dictionary_catalog import DICTIONARY_CATALOGS, get_dictionary_catalog
from apps.references.forms import (
    AvailabilityForm,
    ManufacturerForm,
    PropertyChoiceInlineFormSet,
    PropertyForm,
    TechnologyForm,
)
from apps.references.models import Property, PropertyChoice, PropertyGroup
from apps.workspaces.mixins import AppViewMixin, PermissionRequiredMixin, SystemAdminRequiredMixin
from apps.workspaces.permissions import WorkspacePerm

_DICTIONARY_FORMS = {
    'manufacturers': ManufacturerForm,
    'availabilities': AvailabilityForm,
    'technologies': TechnologyForm,
}


class DictionaryCatalogMixin:
    dictionary_slug = None

    def get_dictionary_config(self):
        config = get_dictionary_catalog(self.dictionary_slug)
        if config is None:
            raise ImproperlyConfigured(f'Unknown dictionary: {self.dictionary_slug}')
        return config

    def get_queryset(self):
        return self.get_dictionary_config()['model'].objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_dictionary_config()
        context['dictionary'] = config
        context['dictionary_slug'] = config['slug']
        return context


class DictionaryHubView(AppViewMixin, PermissionRequiredMixin, TemplateView):
    permission_codename = WorkspacePerm.PROPERTY_VIEW
    template_name = 'references/dictionary_hub.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards = []
        for slug, config in DICTIONARY_CATALOGS.items():
            model = config['model']
            cards.append(
                {
                    **config,
                    'count': model.objects.count(),
                    'list_url': reverse('references:dictionary_list', kwargs={'slug': slug}),
                }
            )
        context['dictionary_cards'] = cards
        return context


class DictionaryListView(
    DictionaryCatalogMixin, AppViewMixin, PermissionRequiredMixin, QuerySetFilterMixin, ListView
):
    permission_codename = WorkspacePerm.PROPERTY_VIEW
    template_name = 'references/dictionary_list.html'
    context_object_name = 'items'
    paginate_by = 30
    search_fields = ('name', 'code', 'description')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('name', 'code', 'description')),
        ('name', 'Название', ('name',)),
        ('code', 'Код', ('code',)),
        ('description', 'Описание', ('description',)),
    )
    search_placeholder = 'Введите текст для поиска...'

    def dispatch(self, request, *args, **kwargs):
        self.dictionary_slug = kwargs.get('slug')
        if get_dictionary_catalog(self.dictionary_slug) is None:
            raise Http404('Справочник не найден')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        config = self.get_dictionary_config()
        related = config['related_name']
        return self.filter_queryset(
            config['model'].objects.annotate(material_count=Count(related)).order_by('name')
        )


class DictionaryCreateView(DictionaryCatalogMixin, SystemAdminRequiredMixin, AppViewMixin, CreateView):
    template_name = 'references/dictionary_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.dictionary_slug = kwargs.get('slug')
        if get_dictionary_catalog(self.dictionary_slug) is None:
            raise Http404('Справочник не найден')
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return _DICTIONARY_FORMS[self.dictionary_slug]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse(
            'references:dictionary_list', kwargs={'slug': self.dictionary_slug}
        )
        return context

    def get_success_url(self):
        return reverse('references:dictionary_list', kwargs={'slug': self.dictionary_slug})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'«{self.object.name}» добавлено в справочник.')
        return response


class DictionaryUpdateView(DictionaryCatalogMixin, SystemAdminRequiredMixin, AppViewMixin, UpdateView):
    template_name = 'references/dictionary_form.html'
    context_object_name = 'item'

    def dispatch(self, request, *args, **kwargs):
        self.dictionary_slug = kwargs.get('slug')
        if get_dictionary_catalog(self.dictionary_slug) is None:
            raise Http404('Справочник не найден')
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return _DICTIONARY_FORMS[self.dictionary_slug]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse(
            'references:dictionary_list', kwargs={'slug': self.dictionary_slug}
        )
        return context

    def get_success_url(self):
        return reverse('references:dictionary_list', kwargs={'slug': self.dictionary_slug})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'«{self.object.name}» сохранено.')
        return response


class DictionaryDeleteView(DictionaryCatalogMixin, SystemAdminRequiredMixin, AppViewMixin, DeleteView):
    template_name = 'references/dictionary_confirm_delete.html'
    context_object_name = 'item'

    def dispatch(self, request, *args, **kwargs):
        self.dictionary_slug = kwargs.get('slug')
        if get_dictionary_catalog(self.dictionary_slug) is None:
            raise Http404('Справочник не найден')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('references:dictionary_list', kwargs={'slug': self.dictionary_slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        related = self.get_dictionary_config()['related_name']
        context['material_count'] = getattr(self.object, related).count()
        return context

    def form_valid(self, form):
        name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f'«{name}» удалено из справочника.')
        return response


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


class PropertyBulkDeleteView(SystemAdminRequiredMixin, AppViewMixin, View):
    template_name = 'includes/bulk_confirm_delete.html'
    max_items = 100

    def get(self, request, *args, **kwargs):
        return redirect('references:list')

    def post(self, request, *args, **kwargs):
        ids = parse_bulk_ids(request, max_items=self.max_items)
        if not ids:
            messages.warning(request, 'Не выбрано ни одного свойства.')
            return redirect('references:list')

        props = list(Property.objects.filter(pk__in=ids))
        by_pk = {str(p.pk): p for p in props}
        deletable = [by_pk[i] for i in ids if i in by_pk]

        if request.POST.get('confirm') != '1':
            return TemplateResponse(
                request,
                self.template_name,
                {
                    'page_title': 'Удаление выбранных свойств',
                    'warning_text': (
                        f'Будут удалены <strong>{len(deletable)}</strong> свойств(а). '
                        'Значения этих свойств у материалов и образцов также будут удалены.'
                    ),
                    'deletable': [
                        {
                            'label': p.display_name,
                            'code': p.name,
                        }
                        for p in deletable
                    ],
                    'blocked': [],
                    'ids': [str(p.pk) for p in deletable],
                    'cancel_url': reverse('references:list'),
                },
            )

        if not deletable:
            messages.warning(request, 'Нет свойств для удаления.')
            return redirect('references:list')

        deleted = 0
        for prop in deletable:
            prop.delete()
            deleted += 1
        messages.success(request, f'Удалено свойств: {deleted}.')
        return redirect('references:list')


class DictionaryBulkDeleteView(DictionaryCatalogMixin, SystemAdminRequiredMixin, AppViewMixin, View):
    template_name = 'includes/bulk_confirm_delete.html'
    max_items = 100

    def dispatch(self, request, *args, **kwargs):
        self.dictionary_slug = kwargs.get('slug')
        if get_dictionary_catalog(self.dictionary_slug) is None:
            raise Http404('Справочник не найден')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return redirect('references:dictionary_list', slug=self.dictionary_slug)

    def post(self, request, *args, **kwargs):
        config = self.get_dictionary_config()
        model = config['model']
        list_url = reverse('references:dictionary_list', kwargs={'slug': self.dictionary_slug})
        ids = parse_bulk_ids(request, max_items=self.max_items)
        if not ids:
            messages.warning(request, 'Не выбрано ни одной записи.')
            return redirect(list_url)

        items = list(model.objects.filter(pk__in=ids))
        by_pk = {str(i.pk): i for i in items}
        deletable = [by_pk[i] for i in ids if i in by_pk]

        if request.POST.get('confirm') != '1':
            return TemplateResponse(
                request,
                self.template_name,
                {
                    'page_title': f'Удаление — {config["label"]}',
                    'warning_text': (
                        f'Будут удалены <strong>{len(deletable)}</strong> запис(ей) справочника «{config["label"]}». '
                        'У материалов эти поля станут пустыми.'
                    ),
                    'deletable': [
                        {'label': item.name, 'code': item.code} for item in deletable
                    ],
                    'blocked': [],
                    'ids': [str(item.pk) for item in deletable],
                    'cancel_url': list_url,
                },
            )

        if not deletable:
            messages.warning(request, 'Нет записей для удаления.')
            return redirect(list_url)

        deleted = 0
        for item in deletable:
            item.delete()
            deleted += 1
        messages.success(request, f'Удалено из «{config["label"]}»: {deleted}.')
        return redirect(list_url)
