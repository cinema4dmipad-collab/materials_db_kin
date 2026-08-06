"""Browser session endpoints for KeenetiX desktop channel (no PAT in the page)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.api.desktop import desktop_status, enqueue_open_scan


@login_required
@ensure_csrf_cookie
@require_GET
def desktop_status_view(request):
    return JsonResponse(desktop_status(request.user))


@login_required
@require_POST
def desktop_open_scan_view(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)
    try:
        cmd = enqueue_open_scan(
            request.user,
            scan_id=str(payload.get('scan_id') or ''),
            workspace_id=str(payload.get('workspace_id') or ''),
        )
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except RuntimeError as exc:
        if str(exc) == 'desktop_offline':
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'desktop_offline',
                    'detail': 'KeenetiX не подключён. Запустите приложение с тем же токеном API.',
                },
                status=503,
            )
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    return JsonResponse({'ok': True, 'command_id': str(cmd.id)})
