from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.backup import (
    BackupError,
    create_volume_dump,
    run_pg_dump,
)
from apps.core.models import BackupRun, BackupSettings
from apps.workspaces.test_utils import AuthenticatedWorkspaceTestCase, DEFAULT_TEST_PASSWORD


User = get_user_model()
FIXED_NOW = datetime(2026, 7, 30, 3, 0, 0, tzinfo=ZoneInfo('Europe/Moscow'))


def fake_dump(output_path):
    Path(output_path).write_bytes(b'PGDUMP')


class BackupPermissionsTests(AuthenticatedWorkspaceTestCase):
    def test_manager_who_is_not_superuser_gets_forbidden(self):
        response = self.client.get(reverse('administration:backups'))

        self.assertEqual(response.status_code, 403)


class BackupAdministrationTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='backup-admin',
            email='backup-admin@example.com',
            password=DEFAULT_TEST_PASSWORD,
        )
        self.client.force_login(self.superuser)

    def test_superuser_can_open_backup_settings(self):
        response = self.client.get(reverse('administration:backups'))

        self.assertEqual(response.status_code, 200)

    def test_superuser_saves_backup_settings(self):
        response = self.client.post(
            reverse('administration:backups'),
            {
                'enabled': 'on',
                'schedule_time': '14:30',
                'retention_count': 12,
            },
        )

        settings = BackupSettings.get_solo()
        self.assertRedirects(response, reverse('administration:backups'))
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.schedule_hour, 14)
        self.assertEqual(settings.schedule_minute, 30)
        self.assertEqual(settings.retention_count, 12)
        self.assertEqual(settings.updated_by, self.superuser)

    def test_manual_backup_returns_attachment_and_removes_temp_file(self):
        with TemporaryDirectory() as backup_dir, override_settings(BACKUP_DIR=backup_dir):
            with (
                patch('apps.core.backup_views.is_postgresql', return_value=True),
                patch('apps.core.backup.run_pg_dump', side_effect=fake_dump),
            ):
                response = self.client.post(reverse('administration:backup_manual'))

            temporary_path = response.temporary_path
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            self.assertEqual(b''.join(response.streaming_content), b'PGDUMP')
            response.close()

            self.assertFalse(temporary_path.exists())
            self.assertEqual(
                BackupRun.objects.get().status,
                BackupRun.Status.SUCCESS,
            )
            self.assertEqual(BackupRun.objects.get().filename, '')

    def test_manual_backup_redirects_when_postgresql_is_unavailable(self):
        with patch('apps.core.backup_views.is_postgresql', return_value=False):
            response = self.client.post(reverse('administration:backup_manual'))
            page_response = self.client.get(reverse('administration:backups'))

        self.assertRedirects(response, reverse('administration:backups'))
        self.assertContains(page_response, 'Для резервного копирования требуется PostgreSQL')


class BackupSchedulingTests(TestCase):
    def test_scheduled_command_creates_one_successful_dump_per_day(self):
        settings = BackupSettings.get_solo()
        settings.enabled = True
        settings.schedule_hour = FIXED_NOW.hour
        settings.schedule_minute = FIXED_NOW.minute
        settings.save()

        with TemporaryDirectory() as backup_dir, override_settings(BACKUP_DIR=backup_dir):
            with (
                patch('apps.core.backup.run_pg_dump', side_effect=fake_dump),
                patch('apps.core.backup.timezone.localtime', return_value=FIXED_NOW),
                patch('django.utils.timezone.localtime', return_value=FIXED_NOW),
            ):
                call_command('run_scheduled_backup')
                call_command('run_scheduled_backup')

            successful_runs = BackupRun.objects.filter(status=BackupRun.Status.SUCCESS)
            dump_files = list(Path(backup_dir).glob('materials_db_*.dump'))
            self.assertEqual(successful_runs.count(), 1)
            self.assertEqual(len(dump_files), 1)
            self.assertEqual(dump_files[0].read_bytes(), b'PGDUMP')

    def test_retention_removes_dumps_exceeding_configured_limit(self):
        retention_count = 2
        settings = BackupSettings.get_solo()
        settings.retention_count = retention_count
        settings.save(update_fields=['retention_count'])
        dump_number = 0

        def distinct_localtime(value=None):
            nonlocal dump_number
            dump_number += 1
            return FIXED_NOW + timedelta(seconds=dump_number)

        with TemporaryDirectory() as backup_dir, override_settings(BACKUP_DIR=backup_dir):
            with (
                patch('apps.core.backup.run_pg_dump', side_effect=fake_dump),
                patch('apps.core.backup.timezone.localtime', side_effect=distinct_localtime),
            ):
                for _ in range(retention_count + 2):
                    create_volume_dump(trigger=BackupRun.Trigger.SCHEDULED)

            dump_files = list(Path(backup_dir).glob('materials_db_*.dump'))
            self.assertEqual(len(dump_files), retention_count)

    def test_run_pg_dump_raises_when_pg_dump_is_missing(self):
        with (
            patch('apps.core.backup.is_postgresql', return_value=True),
            patch('apps.core.backup.shutil.which', return_value=None),
        ):
            with self.assertRaisesRegex(BackupError, 'pg_dump не найдена'):
                run_pg_dump(Path('unused.dump'))

    def test_retention_does_not_delete_temp_manual_dumps(self):
        settings = BackupSettings.get_solo()
        settings.retention_count = 1
        settings.save(update_fields=['retention_count'])

        with TemporaryDirectory() as backup_dir, override_settings(BACKUP_DIR=backup_dir):
            tmp_dir = Path(backup_dir) / 'tmp'
            tmp_dir.mkdir()
            temp_file = tmp_dir / 'materials_db_manual.tmp.dump'
            temp_file.write_bytes(b'TEMP')
            named = Path(backup_dir) / 'materials_db_20260101_010101.dump'
            named.write_bytes(b'OLD')
            newer = Path(backup_dir) / 'materials_db_20260102_010101.dump'
            newer.write_bytes(b'NEW')

            from apps.core.backup import apply_retention

            apply_retention(1)

            self.assertTrue(temp_file.exists())
            self.assertFalse(named.exists())
            self.assertTrue(newer.exists())
