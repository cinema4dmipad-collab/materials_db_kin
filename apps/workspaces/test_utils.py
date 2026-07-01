from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.workspaces.models import BUILTIN_GROUP_MANAGER, Workspace
from apps.workspaces.services import (
    ACTIVE_WORKSPACE_SESSION_KEY,
    assign_user_to_groups,
    ensure_default_groups,
    ensure_legacy_workspace,
)

User = get_user_model()
DEFAULT_TEST_PASSWORD = 'test-pass-123'


def legacy_workspace():
    workspace = ensure_legacy_workspace()
    ensure_default_groups(workspace)
    return workspace


def assign_user_to_groups_by_name(user, workspace, *group_names):
    assign_user_to_groups(user, workspace, group_names)


def create_test_material(**kwargs):
    kwargs.setdefault('home_workspace', legacy_workspace())
    from apps.materials.models import Material

    return Material.objects.create(**kwargs)


def create_test_sample(**kwargs):
    kwargs.setdefault('workspace', legacy_workspace())
    from apps.samples.models import Sample

    return Sample.objects.create(**kwargs)


def create_test_scan(**kwargs):
    kwargs.setdefault('workspace', legacy_workspace())
    from apps.scans.models import ScanRecord

    return ScanRecord.objects.create(**kwargs)


def login_test_client(client: Client, user=None, workspace=None, password=DEFAULT_TEST_PASSWORD):
    if user is None:
        user = User.objects.create_user('testuser', password=password)
    client.login(username=user.username, password=password)
    if workspace is not None:
        session = client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(workspace.pk)
        session.save()
    return user


class AuthenticatedWorkspaceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = DEFAULT_TEST_PASSWORD
        cls.user = User.objects.create_user('workspace-user', password=cls.password)
        cls.workspace = Workspace.objects.create(
            slug='test-ws',
            name='Тестовое пространство',
            description='Для автотестов',
        )
        ensure_default_groups(cls.workspace)
        assign_user_to_groups(cls.user, cls.workspace, [BUILTIN_GROUP_MANAGER])

    def setUp(self):
        self.client = Client()
        login_test_client(self.client, user=self.user, workspace=self.workspace, password=self.password)
