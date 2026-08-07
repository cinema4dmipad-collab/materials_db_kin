"""Build keenetix:// deep links for opening scans in the desktop app."""

from __future__ import annotations

from uuid import UUID


def build_keenetix_scan_url(scan_id, workspace_id) -> str:
    """
    Return ``keenetix://lab/scan/<uuid>?workspace=<uuid>``.

    Raises ValueError if ids are not valid UUIDs.
    """
    scan = str(UUID(str(scan_id)))
    workspace = str(UUID(str(workspace_id)))
    return f'keenetix://lab/scan/{scan}?workspace={workspace}'


def keenetix_scan_url_for(scan) -> str:
    """Build deep link from a ScanRecord (scan.workspace, else sample.workspace)."""
    workspace_id = getattr(scan, 'workspace_id', None)
    if not workspace_id:
        workspace = getattr(scan, 'workspace', None)
        if workspace is not None:
            workspace_id = getattr(workspace, 'pk', None) or workspace
    if not workspace_id:
        sample = getattr(scan, 'sample', None)
        if sample is not None:
            workspace_id = getattr(sample, 'workspace_id', None)
            if not workspace_id:
                sample_ws = getattr(sample, 'workspace', None)
                if sample_ws is not None:
                    workspace_id = getattr(sample_ws, 'pk', None) or sample_ws
    if not workspace_id:
        raise ValueError('Scan has no workspace for KeenetiX deep link')
    return build_keenetix_scan_url(scan.pk, workspace_id)
