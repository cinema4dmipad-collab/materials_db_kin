from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic.edit import FormView

from apps.core.backup import BackupError, create_manual_temp_dump, get_backup_dir, is_postgresql
from apps.core.forms import BackupSettingsForm
from apps.core.models import BackupRun, BackupSettings
from apps.workspaces.mixins import SystemAdminRequiredMixin


class TemporaryBackupFileResponse(FileResponse):
    """Удаляет временный дамп после завершения HTTP-ответа."""

    def __init__(self, *args, temporary_path: Path, **kwargs):
        self.temporary_path = temporary_path
        super().__init__(*args, **kwargs)

    def close(self):
        try:
            super().close()
        finally:
            self.temporary_path.unlink(missing_ok=True)


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
        return context

    def form_valid(self, form):
        settings = form.save(commit=False)
        settings.updated_by = self.request.user
        settings.save()
        messages.success(self.request, 'Настройки резервного копирования сохранены.')
        return super().form_valid(form)


class BackupManualView(SystemAdminRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not is_postgresql():
            messages.error(request, 'Резервное копирование доступно только для PostgreSQL.')
            return redirect('administration:backups')

        dump_path = None
        try:
            backup_run, dump_path = create_manual_temp_dump(request.user)
        except BackupError as exc:
            messages.error(request, str(exc))
            return redirect('administration:backups')

        if backup_run.status != BackupRun.Status.SUCCESS or not dump_path.exists():
            if dump_path is not None:
                dump_path.unlink(missing_ok=True)
            messages.error(
                request,
                backup_run.error_message or 'Не удалось создать резервную копию.',
            )
            return redirect('administration:backups')

        filename = f'materials_db_{timezone.localtime(backup_run.started_at):%Y%m%d_%H%M%S}.dump'
        try:
            response = TemporaryBackupFileResponse(
                dump_path.open('rb'),
                as_attachment=True,
                filename=filename,
                temporary_path=dump_path,
            )
        except OSError:
            dump_path.unlink(missing_ok=True)
            messages.error(request, 'Не удалось открыть файл резервной копии.')
            return redirect('administration:backups')

        backup_run.filename = ''
        backup_run.save(update_fields=['filename'])
        return response

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class BackupDownloadView(SystemAdminRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        backup_run = get_object_or_404(
            BackupRun,
            pk=pk,
            trigger=BackupRun.Trigger.SCHEDULED,
            status=BackupRun.Status.SUCCESS,
        )
        if not backup_run.filename:
            raise Http404('Файл резервной копии не найден.')

        backup_dir = get_backup_dir().resolve()
        backup_path = (backup_dir / backup_run.filename).resolve()
        if backup_path.parent != backup_dir or not backup_path.is_file():
            raise Http404('Файл резервной копии не найден.')

        return FileResponse(
            backup_path.open('rb'),
            as_attachment=True,
            filename=backup_path.name,
        )
