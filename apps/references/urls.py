from django.urls import path

from apps.references.views import (
    DictionaryBulkDeleteView,
    DictionaryCreateView,
    DictionaryDeleteView,
    DictionaryHubView,
    DictionaryListView,
    DictionaryUpdateView,
    PropertyBulkDeleteView,
    PropertyCreateView,
    PropertyDeleteView,
    PropertyGroupCreateView,
    PropertyGroupDeleteView,
    PropertyGroupListView,
    PropertyGroupUpdateView,
    PropertyListView,
    PropertyUpdateView,
)

app_name = 'references'

urlpatterns = [
    path('', PropertyListView.as_view(), name='list'),
    path('create/', PropertyCreateView.as_view(), name='create'),
    path('bulk-delete/', PropertyBulkDeleteView.as_view(), name='bulk_delete'),
    path('groups/', PropertyGroupListView.as_view(), name='group_list'),
    path('groups/create/', PropertyGroupCreateView.as_view(), name='group_create'),
    path('groups/<uuid:pk>/edit/', PropertyGroupUpdateView.as_view(), name='group_edit'),
    path('groups/<uuid:pk>/delete/', PropertyGroupDeleteView.as_view(), name='group_delete'),
    path('dictionaries/', DictionaryHubView.as_view(), name='dictionary_hub'),
    path(
        'dictionaries/<slug:slug>/',
        DictionaryListView.as_view(),
        name='dictionary_list',
    ),
    path(
        'dictionaries/<slug:slug>/create/',
        DictionaryCreateView.as_view(),
        name='dictionary_create',
    ),
    path(
        'dictionaries/<slug:slug>/bulk-delete/',
        DictionaryBulkDeleteView.as_view(),
        name='dictionary_bulk_delete',
    ),
    path(
        'dictionaries/<slug:slug>/<uuid:pk>/edit/',
        DictionaryUpdateView.as_view(),
        name='dictionary_edit',
    ),
    path(
        'dictionaries/<slug:slug>/<uuid:pk>/delete/',
        DictionaryDeleteView.as_view(),
        name='dictionary_delete',
    ),
    path('<uuid:pk>/edit/', PropertyUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', PropertyDeleteView.as_view(), name='delete'),
]
