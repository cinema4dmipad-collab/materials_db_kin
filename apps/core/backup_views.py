from pathlib import Path
import tempfile

from django.contrib import messages
from django.db import connections
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic.edit import FormView

from apps.core.backup import (
    BackupError,
    cancel_running_backups,
    create_manual_volume_dump,
    get_backup_dir,
    get_running_backup,
    get_temp_dir,
    is_postgresql,
    restore_from_dump,
)
from apps.core.forms import BackupRestoreForm, BackupSettingsForm
from apps.core.models import BackupRun, BackupSettings
from apps.workspaces.mixins import SystemAdminRequiredMixin


class BackupSettingsView(SystemAdminRequiredMixin, FormView):
    template_name = 'core/backups.html'
    form_class = BackupSettingsForm
    success_url = reverse_lazy('administration:backups')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = BackupSettings.get_solo()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['backup_runs'] = BackupRun.objects.all()[:20]
        context['postgresql_available'] = is_postgresql()
        context['is_postgresql'] = context['postgresql_available']
        context['restore_form'] = kwargs.get('restore_form') or BackupRestoreForm()
        context['running_backup'] = get_running_backup()
        return context

    def form_valid(self, form):
        settings_obj = form.save(commit=False)
        settings_obj.updated_by = self.request.user
        settings_obj.save()
        messages.success(self.request, 'Настройки резервного копирования сохранены.')
        return super().form_valid(form)


class BackupManualView(SystemAdminRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not is_postgresql():
            messages.error(request, 'Резервное копирование доступно только для PostgreSQL.')
            return redirect('administration:backups')

        try:
            backup_run = create_manual_volume_dump(request.user)
        except BackupError as exc:
            messages.error(request, str(exc))
            return redirect('administration:backups')

        if backup_run is None or backup_run.status != BackupRun.Status.SUCCESS:
            messages.error(
                request,
                getattr(backup_run, 'error_message', None) or 'Не удалось создать резервную копию.',
            )
            return redirect('administration:backups')

        # Файл лежит на томе — отдельный GET можно повторить, если браузер оборвал связь.
        messages.success(
            request,
            'Дамп создан. Если скачивание оборвалось — нажмите «Скачать» в таблице запусков.',
        )
        return redirect('administration:backup_download', pk=backup_run.pk)

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class BackupRestoreView(SystemAdminRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not is_postgresql():
            messages.error(request, 'Восстановление доступно только для PostgreSQL.')
            return redirect('administration:backups')

        form = BackupRestoreForm(request.POST, request.FILES)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
            return redirect('administration:backups')

        uploaded = form.cleaned_data['dump_file']
        target = None
        try:
            get_temp_dir()
            with tempfile.NamedTemporaryFile(
                suffix='.dump',
                prefix='restore_',
                dir=get_temp_dir(),
                delete=False,
            ) as temporary_file:
                target = Path(temporary_file.name)
                for chunk in uploaded.chunks():
                    temporary_file.write(chunk)

            connections.close_all()
            restore_from_dump(
                dump_path=target,
                original_name=uploaded.name,
                user=request.user if request.user.is_authenticated else None,
            )
            messages.success(
                request,
                'Дамп успешно восстановлен. Рекомендуется обновить страницу и проверить данные.',
            )
        except BackupError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Не удалось восстановить дамп: {exc}')
        finally:
            if target is not None:
                target.unlink(missing_ok=True)

        return redirect('administration:backups')

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class BackupCancelRunningView(SystemAdminRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        cancelled = cancel_running_backups()
        if cancelled:
            messages.success(
                request,
                f'Отменено зависших запусков: {cancelled}. Можно снова сделать дамп.',
            )
        else:
            messages.info(request, 'Активных запусков не найдено.')
        return redirect('administration:backups')

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class BackupDownloadView(SystemAdminRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        backup_run = get_object_or_404(
            BackupRun,
            pk=pk,
            trigger__in=(BackupRun.Trigger.SCHEDULED, BackupRun.Trigger.MANUAL),
            status=BackupRun.Status.SUCCESS,
        )
        if not backup_run.filename:
            raise Http404('Файл резервной копии не найден.')

        backup_dir = get_backup_dir().resolve()
        backup_path = (backup_dir / backup_run.filename).resolve()
        if backup_path.parent != backup_dir or not backup_path.is_file():
            raise Http404('Файл резервной копии не найден.')

        response = FileResponse(
            backup_path.open('rb'),
            as_attachment=True,
            filename=backup_path.name,
        )
        response['Content-Length'] = backup_path.stat().st_size
        return response
