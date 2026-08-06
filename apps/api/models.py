"""API-side models (KeenetiX desktop session channel)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class KeenetiXDesktopSession(models.Model):
    """One active KeenetiX desktop per user; last connect wins."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='keenetix_desktop_sessions',
    )
    device_id = models.CharField(max_length=64, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'device_id'],
                name='uniq_keenetix_desktop_user_device',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'is_active', '-last_seen_at']),
        ]

    def __str__(self) -> str:
        state = 'active' if self.is_active else 'idle'
        return f'KeenetiXDesktopSession({self.user_id}, {self.device_id}, {state})'


class KeenetiXDesktopCommand(models.Model):
    """Queued control command for the active desktop of a user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='keenetix_desktop_commands',
    )
    command = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'delivered_at', 'created_at']),
        ]
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'KeenetiXDesktopCommand({self.command}, user={self.user_id})'
