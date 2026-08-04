import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from dmr.security.token.app.models import Token

from apps.scans.test_utils import make_hdf5_upload
from apps.structures.models import StructureType
from apps.workspaces.models import BUILTIN_GROUP_OPERATOR, Workspace
from apps.workspaces.services import assign_user_to_groups, ensure_default_groups
from apps.workspaces.test_utils import (
    DEFAULT_TEST_PASSWORD,
    create_test_material,
    create_test_sample,
    create_test_scan,
)

User = get_user_model()


class ApiV1Tests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
            },
        )
        self.settings_override.enable()

        self.password = DEFAULT_TEST_PASSWORD
        self.user = User.objects.create_user('api-user', password=self.password)
        self.other = User.objects.create_user('api-other', password=self.password)
        self.workspace = Workspace.objects.create(slug='api-ws', name='API WS')
        self.other_ws = Workspace.objects.create(slug='api-other-ws', name='Other WS')
        ensure_default_groups(self.workspace)
        ensure_default_groups(self.other_ws)
        assign_user_to_groups(self.user, self.workspace, [BUILTIN_GROUP_OPERATOR])
        assign_user_to_groups(self.other, self.other_ws, [BUILTIN_GROUP_OPERATOR])
        self.structure_type = StructureType.objects.create(
            name='API Structure',
            code='api_structure',
            table_name='api_structure_table',
            is_created=True,
        )
        self.material = create_test_material(
            code='API-M1',
            name='API Material',
            home_workspace=self.workspace,
        )
        self.material.struct_type = self.structure_type
        self.material.save(update_fields=['struct_type'])
        self.sample = create_test_sample(
            code='API-S1',
            name='API Sample',
            material=self.material,
            workspace=self.workspace,
        )
        self.scan = create_test_scan(
            sample=self.sample,
            workspace=self.workspace,
            title='API Scan',
            file=make_hdf5_upload('api.h5'),
        )
        self.token_obj, self.raw_token = Token.issue(user=self.user, name='keenetix')
        self.client = Client()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _headers(self, *, token=None, workspace=None):
        headers = {
            'HTTP_AUTHORIZATION': f'Bearer {token or self.raw_token}',
        }
        if workspace is not False:
            headers['HTTP_X_WORKSPACE_ID'] = str((workspace or self.workspace).pk)
        return headers

    def test_workspaces_requires_token(self):
        response = self.client.get(reverse('api:workspaces'))
        self.assertEqual(response.status_code, 401)

    def test_workspaces_list(self):
        response = self.client.get(
            reverse('api:workspaces'),
            **self._headers(workspace=False),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item['id'] for item in payload}
        self.assertIn(str(self.workspace.pk), ids)
        self.assertNotIn(str(self.other_ws.pk), ids)

    def test_materials_list_and_detail(self):
        response = self.client.get(reverse('api:materials'), **self._headers())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['meta']['count'], 1)
        self.assertEqual(data['results'][0]['code'], 'API-M1')
        self.assertEqual(data['results'][0]['struct_type_id'], self.structure_type.pk)

        detail = self.client.get(
            reverse('api:material_detail', kwargs={'material_id': self.material.pk}),
            **self._headers(),
        )
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body['id'], str(self.material.pk))
        self.assertIn('properties', body)
        self.assertEqual(body['structure']['type_id'], self.structure_type.pk)
        self.assertEqual(body['structure']['type_code'], 'api_structure')

    def test_foreign_workspace_returns_404(self):
        response = self.client.get(
            reverse('api:materials'),
            **self._headers(workspace=self.other_ws),
        )
        self.assertEqual(response.status_code, 404)

    def test_samples_and_scans(self):
        samples = self.client.get(reverse('api:samples'), **self._headers())
        self.assertEqual(samples.status_code, 200)
        self.assertEqual(samples.json()['meta']['count'], 1)
        self.assertEqual(samples.json()['results'][0]['scans_count'], 1)

        by_code = self.client.get(
            reverse('api:samples'),
            {'search': self.sample.code},
            **self._headers(),
        )
        self.assertEqual(by_code.status_code, 200)
        self.assertEqual(by_code.json()['meta']['count'], 1)

        miss = self.client.get(
            reverse('api:samples'),
            {'search': 'definitely-missing-sample-xyz'},
            **self._headers(),
        )
        self.assertEqual(miss.status_code, 200)
        self.assertEqual(miss.json()['meta']['count'], 0)

        scans = self.client.get(reverse('api:scans'), **self._headers())
        self.assertEqual(scans.status_code, 200)
        self.assertEqual(scans.json()['meta']['count'], 1)
        self.assertTrue(scans.json()['results'][0]['download_url'].endswith('/download/'))

    def test_scan_download_streams(self):
        response = self.client.get(
            reverse('api:scan_download', kwargs={'scan_id': self.scan.pk}),
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        content = b''.join(response.streaming_content)
        self.assertTrue(content.startswith(b'\x89HDF\r\n\x1a\n'))

    def test_create_scan_for_sample(self):
        response = self.client.post(
            reverse('api:sample_scans_create', kwargs={'sample_id': self.sample.pk}),
            data={
                'file': make_hdf5_upload('from-keenetix.h5'),
                'title': 'From KeenetiX',
                'method': 'echo',
                'description': 'uploaded via API',
            },
            **self._headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['title'], 'From KeenetiX')
        self.assertEqual(body['sample_id'], str(self.sample.pk))

    def test_token_create_on_profile(self):
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(
            reverse('accounts:token_create'),
            {'name': 'postman', 'expires_in_days': 7},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Token.objects.filter(user=self.user, name='postman').exists())
        self.assertContains(response, 'api-token-secret-modal')
        self.assertContains(response, 'data-token-secret=')
        self.assertContains(response, 'Скопировать')
        # Flash once: повторный заход в профиль не должен снова открывать секрет.
        again = self.client.get(reverse('accounts:profile'))
        self.assertNotContains(again, 'data-token-secret=')
        self.assertIsNone(self.client.session.get('api_token_plaintext'))
