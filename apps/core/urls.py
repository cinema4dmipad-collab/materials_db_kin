from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('debug/', views.debug_page, name='debug'),
    path('help/', views.help_page, name='help'),
]
