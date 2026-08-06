"""KeenetiX desktop session channel — last connect for a user wins."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.api.models import KeenetiXDesktopCommand, KeenetiXDesktopSession

# Desktop is "online" only while is_active and heartbeated within this window.
# Poll interval is ~10s; keep a small grace for jitter. Explicit disconnect
# clears is_active immediately (no need to wait for TTL).
ONLINE_TTL = timedelta(seconds=20)


def connect_desktop(user: AbstractBaseUser, device_id: str) -> KeenetiXDesktopSession:
    device_id = (device_id or '').strip()
    if not device_id or len(device_id) > 64:
        raise ValueError('invalid_device_id')
    with transaction.atomic():
        KeenetiXDesktopSession.objects.filter(user=user, is_active=True).exclude(
            device_id=device_id
        ).update(is_active=False)
        session, _created = KeenetiXDesktopSession.objects.update_or_create(
            user=user,
            device_id=device_id,
            defaults={'is_active': True},
        )
        # Touch last_seen even on update_or_create when defaults unchanged.
        KeenetiXDesktopSession.objects.filter(pk=session.pk).update(
            is_active=True,
            last_seen_at=timezone.now(),
        )
        session.refresh_from_db()
    return session


def heartbeat_desktop(user: AbstractBaseUser, device_id: str) -> bool:
    """Return True if this device is still the active desktop."""
    device_id = (device_id or '').strip()
    updated = KeenetiXDesktopSession.objects.filter(
        user=user,
        device_id=device_id,
        is_active=True,
    ).update(last_seen_at=timezone.now())
    return bool(updated)


def disconnect_desktop(user: AbstractBaseUser, device_id: str) -> bool:
    """Mark this device offline immediately. Returns True if a row was updated."""
    device_id = (device_id or '').strip()
    if not device_id or len(device_id) > 64:
        raise ValueError('invalid_device_id')
    updated = KeenetiXDesktopSession.objects.filter(
        user=user,
        device_id=device_id,
        is_active=True,
    ).update(is_active=False, last_seen_at=timezone.now())
    return bool(updated)


def active_desktop(user: AbstractBaseUser) -> KeenetiXDesktopSession | None:
    cutoff = timezone.now() - ONLINE_TTL
    return (
        KeenetiXDesktopSession.objects.filter(
            user=user,
            is_active=True,
            last_seen_at__gte=cutoff,
        )
        .order_by('-last_seen_at')
        .first()
    )


def desktop_status(user: AbstractBaseUser) -> dict[str, Any]:
    session = active_desktop(user)
    if session is None:
        return {'online': False, 'device_id': None}
    return {
        'online': True,
        'device_id': session.device_id,
        'last_seen_at': session.last_seen_at.isoformat(),
    }


def enqueue_open_scan(
    user: AbstractBaseUser,
    *,
    scan_id: str,
    workspace_id: str = '',
) -> KeenetiXDesktopCommand:
    try:
        scan_uuid = str(UUID(str(scan_id)))
    except ValueError as exc:
        raise ValueError('invalid_scan_id') from exc
    workspace = (workspace_id or '').strip()
    if workspace:
        try:
            workspace = str(UUID(workspace))
        except ValueError as exc:
            raise ValueError('invalid_workspace_id') from exc
    if active_desktop(user) is None:
        raise RuntimeError('desktop_offline')
    return KeenetiXDesktopCommand.objects.create(
        user=user,
        command='open_scan',
        payload={'scan_id': scan_uuid, 'workspace_id': workspace},
    )


def claim_commands(user: AbstractBaseUser, device_id: str) -> list[dict[str, Any]]:
    """Return pending commands only for the active device; mark delivered."""
    device_id = (device_id or '').strip()
    session = (
        KeenetiXDesktopSession.objects.filter(
            user=user,
            device_id=device_id,
            is_active=True,
        )
        .first()
    )
    if session is None:
        return []
    # Heartbeat on poll.
    KeenetiXDesktopSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())
    if session.last_seen_at < timezone.now() - ONLINE_TTL:
        # Stale before update — still allow claim after heartbeat above.
        pass
    with transaction.atomic():
        qs = (
            KeenetiXDesktopCommand.objects.select_for_update()
            .filter(user=user, delivered_at__isnull=True)
            .order_by('created_at')[:20]
        )
        rows = list(qs)
        now = timezone.now()
        ids = [row.pk for row in rows]
        if ids:
            KeenetiXDesktopCommand.objects.filter(pk__in=ids).update(delivered_at=now)
    return [
        {
            'id': str(row.id),
            'command': row.command,
            'payload': row.payload or {},
            'created_at': row.created_at.isoformat(),
        }
        for row in rows
    ]
