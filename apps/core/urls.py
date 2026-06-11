from django.urls import path

from . import views
from .tag_views import TagCreateView, TagDeleteView, TagListView, TagUpdateView

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('debug/', views.debug_page, name='debug'),
    path('help/', views.help_page, name='help'),
    path('tags/', TagListView.as_view(), name='tag_list'),
    path('tags/create/', TagCreateView.as_view(), name='tag_create'),
    path('tags/<uuid:pk>/edit/', TagUpdateView.as_view(), name='tag_edit'),
    path('tags/<uuid:pk>/delete/', TagDeleteView.as_view(), name='tag_delete'),
]
