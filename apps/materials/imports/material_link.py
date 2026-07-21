from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from apps.materials.models import Material
from apps.materials.picker_data import materials_for_picker_queryset
from apps.workspaces.models import Workspace


@dataclass
class MaterialLinkIndex:
    """Lookup for resolving material refs against DB + in-batch drafts."""

    by_code: dict[str, str] = field(default_factory=dict)  # casefold code → display code
    by_name: dict[str, list[str]] = field(default_factory=dict)  # casefold name → codes

    @classmethod
    def from_drafts(cls, drafts) -> MaterialLinkIndex:
        index = cls()
        for draft in drafts:
            if getattr(draft, 'action', None) == 'skip':
                continue
            code = (getattr(draft, 'code', None) or '').strip()
            name = (getattr(draft, 'name', None) or '').strip()
            if code:
                index.by_code[code.casefold()] = code
            if name and code:
                index.by_name.setdefault(name.casefold(), [])
                if code not in index.by_name[name.casefold()]:
                    index.by_name[name.casefold()].append(code)
        return index

    @classmethod
    def from_import_items(cls, items) -> MaterialLinkIndex:
        index = cls()
        for item in items:
            code = (getattr(item, 'code', None) or '').strip()
            name = (getattr(item, 'name', None) or '').strip()
            if code:
                index.by_code[code.casefold()] = code
            if name and code:
                index.by_name.setdefault(name.casefold(), [])
                if code not in index.by_name[name.casefold()]:
                    index.by_name[name.casefold()].append(code)
        return index


def ensure_material_ref_known(
    raw,
    *,
    workspace: Workspace,
    draft_index: MaterialLinkIndex | None = None,
) -> str:
    """
    Validate that raw can be resolved (now or after batch create).
    Returns normalized text. Raises ValidationError if unknown/ambiguous.
    """
    text = _normalize_ref(raw)
    if not text:
        raise ValidationError('Укажите код, название или UUID материала.')

    try:
        resolve_material_ref(text, workspace=workspace)
        return text
    except ValidationError as exc:
        if draft_index and _matches_draft_index(text, draft_index):
            return text
        raise exc


def resolve_material_ref(
    raw,
    *,
    workspace: Workspace,
    cache: dict[str, Material | None] | None = None,
) -> Material:
    """
    Resolve cell text to a Material visible in the workspace.
    Accepts UUID, code (case-insensitive), or unique name (case-insensitive).
    """
    text = _normalize_ref(raw)
    if not text:
        raise ValidationError('Укажите код, название или UUID материала.')

    cache_key = text.casefold()
    if cache is not None and cache_key in cache:
        material = cache[cache_key]
        if material is None:
            raise ValidationError(f'Материал «{text}» не найден в пространстве.')
        return material

    qs = materials_for_picker_queryset(workspace)
    material: Material | None = None

    as_uuid = _try_uuid(text)
    if as_uuid is not None:
        material = qs.filter(pk=as_uuid).first()
        if material is None:
            err = ValidationError(f'Материал с UUID «{text}» не найден в пространстве.')
            if cache is not None:
                cache[cache_key] = None
            raise err
    else:
        by_code = list(qs.filter(code__iexact=text)[:2])
        if len(by_code) == 1:
            material = by_code[0]
        elif len(by_code) > 1:
            raise ValidationError(f'Неоднозначный код материала «{text}».')
        else:
            by_name = list(qs.filter(name__iexact=text)[:3])
            if len(by_name) == 1:
                material = by_name[0]
            elif len(by_name) > 1:
                codes = ', '.join(item.code for item in by_name[:5])
                raise ValidationError(
                    f'Название «{text}» неоднозначно (коды: {codes}). Укажите код или UUID.'
                )
            else:
                err = ValidationError(
                    f'Материал «{text}» не найден. Укажите код, уникальное название или UUID.'
                )
                if cache is not None:
                    cache[cache_key] = None
                raise err

    if cache is not None:
        cache[cache_key] = material
    return material


def _matches_draft_index(text: str, draft_index: MaterialLinkIndex) -> bool:
    as_uuid = _try_uuid(text)
    if as_uuid is not None:
        return False  # drafts do not have UUID until created
    if text.casefold() in draft_index.by_code:
        return True
    names = draft_index.by_name.get(text.casefold()) or []
    if len(names) == 1:
        return True
    if len(names) > 1:
        raise ValidationError(
            f'Название «{text}» неоднозначно в файле импорта '
            f'(коды: {", ".join(names[:5])}). Укажите код.'
        )
    return False


def _normalize_ref(raw) -> str:
    if raw is None:
        return ''
    return str(raw).replace('\u00a0', ' ').strip()


def _try_uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(text)
    except (ValueError, TypeError, AttributeError):
        pass
    if len(text) == 32:
        try:
            return uuid.UUID(hex=text)
        except ValueError:
            return None
    return None
