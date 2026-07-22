"""Shared helpers for list bulk-select / bulk-delete."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BulkDeleteResult:
    deleted: list[str] = field(default_factory=list)
    skipped_forbidden: list[str] = field(default_factory=list)
    skipped_protected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)


def parse_bulk_ids(request, *, max_items: int = 100) -> list[str]:
    raw = request.POST.getlist('ids')
    seen: set[str] = set()
    ids: list[str] = []
    for value in raw:
        key = (value or '').strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ids.append(key)
        if len(ids) >= max_items:
            break
    return ids
