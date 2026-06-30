from django.db import models


class VisibilityMode(models.TextChoices):
    PRIVATE = 'private', 'Только домашнее пространство'
    SELECTED_WORKSPACES = 'selected_workspaces', 'Выбранные пространства'
    ALL_WORKSPACES = 'all_workspaces', 'Все пространства'


class WorkspaceVisibilityMixin:
    def is_visible_in(self, workspace):
        if workspace is None:
            return False
        if self.home_workspace_id == workspace.pk:
            return True
        if self.visibility_mode == VisibilityMode.ALL_WORKSPACES:
            return True
        if self.visibility_mode == VisibilityMode.SELECTED_WORKSPACES:
            return self.published_workspaces.filter(pk=workspace.pk).exists()
        return False

    def is_editable_in(self, workspace):
        if workspace is None:
            return False
        if self.home_workspace_id is None:
            return True
        return self.home_workspace_id == workspace.pk
