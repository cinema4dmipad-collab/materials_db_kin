from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.bookmarks import (
    bookmark_context,
    list_resolved_bookmarks,
    sidebar_bookmark_items,
    toggle_bookmark,
)
from apps.core.models import UserBookmark
from apps.workspaces.mixins import AppViewMixin


def _safe_next_url(request, fallback_name='core:dashboard'):
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return reverse(fallback_name)


class BookmarkToggleView(AppViewMixin, View):
    http_method_names = ['post']

    def post(self, request):
        entity_type = (request.POST.get('entity_type') or '').strip()
        entity_id = (request.POST.get('entity_id') or '').strip()
        parent_id = (request.POST.get('parent_id') or '').strip() or None
        context_slug = (request.POST.get('context_slug') or '').strip() or None
        next_url = _safe_next_url(request)

        if not entity_type or not entity_id:
            messages.error(request, 'Не удалось изменить закладку: не указан объект.')
            return redirect(next_url)

        try:
            result = toggle_bookmark(
                user=request.user,
                workspace=request.active_workspace,
                entity_type=entity_type,
                entity_id=entity_id,
                parent_id=parent_id,
                context_slug=context_slug,
            )
        except PermissionDenied:
            raise
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        if result.removed:
            messages.success(request, 'Убрано из закладок.')
        else:
            messages.success(request, 'Добавлено в закладки.')

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(
                {
                    'ok': True,
                    'removed': result.removed,
                    'is_bookmarked': not result.removed,
                }
            )
        return redirect(next_url)


class BookmarkListView(AppViewMixin, View):
    template_name = 'core/bookmark_list.html'

    def get(self, request):
        bookmarks = list_resolved_bookmarks(
            user=request.user,
            workspace=request.active_workspace,
        )
        return render(
            request,
            self.template_name,
            {'bookmarks': bookmarks},
        )


class BookmarkRemoveView(AppViewMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        bookmark = get_object_or_404(
            UserBookmark,
            pk=pk,
            user=request.user,
            workspace=request.active_workspace,
        )
        bookmark.delete()
        messages.success(request, 'Закладка удалена.')
        next_url = _safe_next_url(request, fallback_name='core:bookmark_list')
        return redirect(next_url)
