from django.shortcuts import render

from apps.materials.models import Material
from apps.samples.models import Sample


def dashboard(request):
    context = {
        'materials_count': Material.objects.count(),
        'samples_count': Sample.objects.count(),
        'recent_materials': Material.objects.order_by('-created_at')[:5],
    }
    return render(request, 'core/dashboard.html', context)
