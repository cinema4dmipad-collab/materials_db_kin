from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.services import ACTIVE_WORKSPACE_SESSION_KEY, ensure_legacy_workspace

User = get_user_model()
DEFAULT_TEST_PASSWORD = 'test-pass-123'


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
        cls.membership = WorkspaceMembership.objects.create(
            workspace=cls.workspace,
            user=cls.user,
            role=WorkspaceRole.MANAGER,
        )

    def setUp(self):
        self.client = Client()
        login_test_client(self.client, user=self.user, workspace=self.workspace, password=self.password)
