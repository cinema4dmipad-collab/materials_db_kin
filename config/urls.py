from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.scans.views import AllScansListView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('materials/', include('apps.materials.urls')),
    path('materials/<uuid:material_pk>/attachments/', include('apps.materials.attachment_urls')),
    path('materials/<uuid:material_pk>/samples/', include('apps.materials.sample_urls')),
    path('samples/', include('apps.samples.urls')),
    path('scans/', AllScansListView.as_view(), name='scans_all'),
    path('samples/<uuid:sample_pk>/scans/', include('apps.scans.urls')),
    path('samples/<uuid:sample_pk>/attachments/', include('apps.samples.attachment_urls')),
    path('structures/', include('apps.structures.urls')),
    path('properties/', include('apps.references.urls')),
]

if settings.DEBUG:
    urlpatterns.append(path('__debug__/', include('debug_toolbar.urls')))
