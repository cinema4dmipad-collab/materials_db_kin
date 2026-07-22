"""Lookup helpers for global material metadata dictionaries."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.references.models import Availability, Manufacturer, Technology
from apps.structures.identifiers import normalize_identifier

DICTIONARY_MODELS = {
    'manufacturer': Manufacturer,
    'availability': Availability,
    'technology': Technology,
}

DICTIONARY_LABELS = {
    Manufacturer: 'Производитель',
    Availability: 'Доступность',
    Technology: 'Технология',
}


@dataclass
class DictionaryResolveResult:
    item: object | None = None
    """Existing DB row, or None when creation is deferred (dry-run)."""
    create_name: str | None = None
    """Display name to create on apply when item is None and creation is planned."""
    create_code: str | None = None
    matched_existing: bool = False
    linked_by_code: bool = False
    deferred_create: bool = False
    error: str | None = None


def resolve_dictionary_item(model, raw: str | None, *, active_only: bool = True):
    """Resolve by code or name (case-insensitive). Returns None for blank input.

    ``active_only`` is kept for call-site compatibility; dictionaries no longer
    have an active flag, so it is ignored.
    """
    text = (raw or '').strip()
    if not text:
        return None
    matches = list(
        model.objects.filter(Q(code__iexact=text) | Q(name__iexact=text)).order_by('name')[:2]
    )
    if not matches:
        return None
    return matches[0]


def _find_existing(model, *, text: str, code: str):
    """Find a row that would collide on name or code (case-insensitive)."""
    matches = list(
        model.objects.filter(
            Q(code__iexact=text) | Q(name__iexact=text) | Q(code__iexact=code) | Q(name__iexact=code)
        )
        .order_by('name')
        .distinct()[:2]
    )
    if not matches:
        return None, False
    if len(matches) > 1:
        return matches, True
    return matches[0], False


def _create_or_reuse(model, *, text: str, code: str, label: str) -> DictionaryResolveResult:
    """Insert a row; on unique conflict reuse the existing one (never fail if found)."""
    try:
        with transaction.atomic():
            item = model.objects.create(name=text, code=code)
        return DictionaryResolveResult(item=item)
    except IntegrityError as exc:
        existing, ambiguous = _find_existing(model, text=text, code=code)
        if ambiguous:
            names = ', '.join(f'«{item.name}»' for item in existing)
            return DictionaryResolveResult(
                error=(
                    f'{label}: значение «{text}» неоднозначно совпадает с несколькими '
                    f'записями справочника ({names}). Уточните в файле или в справочнике.'
                )
            )
        if existing is not None:
            return DictionaryResolveResult(item=existing, linked_by_code=True)
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ''
        if 'NOT NULL' in detail.upper() or 'null' in detail.lower():
            return DictionaryResolveResult(
                error=(
                    f'{label} «{text}»: схема БД устарела (не применены миграции справочников). '
                    f'Выполните: python manage.py migrate references. ({detail})'
                )
            )
        return DictionaryResolveResult(
            error=(
                f'{label} «{text}»: не удалось создать запись в справочнике'
                + (f' ({detail})' if detail else '')
                + '. Проверьте справочник и миграции.'
            )
        )


def resolve_or_create_dictionary_item(
    model,
    raw: str | None,
    *,
    create_missing: bool,
    dry_run: bool,
    pending: dict,
) -> DictionaryResolveResult:
    """Resolve by name/code; optionally plan a new dictionary row (never insert here).

    Missing values with ``create_missing=True`` are always **deferred**
    (``deferred_create`` + pending). Inserts happen in
    ``materialize_pending_dictionary`` during import apply inside
    ``transaction.atomic``, so a failed import does not leave orphans.

    Duplicate guards:
    - case-insensitive name or code match → reuse existing;
    - ambiguous (2+ rows match the raw text) → error;
    - normalized code collides with another row → reuse that row (linked_by_code);
    - several file values share one code → one pending create, later rows reuse it.
    """
    text = (raw or '').strip()
    if not text:
        return DictionaryResolveResult()

    label = DICTIONARY_LABELS.get(model, model.__name__)
    matches = list(
        model.objects.filter(Q(code__iexact=text) | Q(name__iexact=text)).order_by('name')[:2]
    )
    if len(matches) > 1:
        names = ', '.join(f'«{item.name}»' for item in matches)
        return DictionaryResolveResult(
            error=(
                f'{label}: значение «{text}» неоднозначно совпадает с несколькими '
                f'записями справочника ({names}). Уточните в файле или в справочнике.'
            )
        )
    if matches:
        return DictionaryResolveResult(item=matches[0], matched_existing=True)

    if not create_missing:
        return DictionaryResolveResult(
            error=f'{label} «{text}» не найден(а) в справочнике.',
        )

    code = normalize_identifier(text, max_length=64)
    if not code:
        return DictionaryResolveResult(
            error=f'{label} «{text}»: не удалось получить латинский код из названия.',
        )

    name_key = (model.__name__, 'name', text.casefold())
    code_key = (model.__name__, 'code', code.casefold())
    if name_key in pending:
        return pending[name_key]
    if code_key in pending:
        return pending[code_key]

    by_code = list(model.objects.filter(code__iexact=code).order_by('name')[:2])
    if len(by_code) > 1:
        return DictionaryResolveResult(
            error=(
                f'{label}: код «{code}» (из «{text}») совпадает с несколькими записями. '
                f'Исправьте справочник.'
            )
        )
    if by_code:
        result = DictionaryResolveResult(item=by_code[0], linked_by_code=True)
        pending[name_key] = result
        pending[code_key] = result
        return result

    # Always defer inserts: validate runs outside the import transaction.
    # Rows are created in apply via materialize_pending_dictionary (inside atomic),
    # so a failed import does not leave orphan dictionary entries.
    # ``dry_run`` is kept for call-site compatibility; creation is deferred either way.
    _ = dry_run
    result = DictionaryResolveResult(
        create_name=text,
        create_code=code,
        deferred_create=True,
    )
    pending[name_key] = result
    pending[code_key] = result
    return result


def materialize_pending_dictionary(model, create_name: str, create_code: str, pending: dict):
    """Create a deferred dictionary row during apply (after dry-run)."""
    name_key = (model.__name__, 'name', create_name.casefold())
    code_key = (model.__name__, 'code', create_code.casefold())
    cached = pending.get(name_key) or pending.get(code_key)
    if cached is not None and getattr(cached, 'pk', None):
        return cached
    if isinstance(cached, DictionaryResolveResult) and cached.item is not None:
        pending[name_key] = cached.item
        pending[code_key] = cached.item
        return cached.item

    existing, ambiguous = _find_existing(model, text=create_name, code=create_code)
    if ambiguous:
        raise IntegrityError(
            f'Неоднозначное совпадение для «{create_name}» / «{create_code}» в справочнике.'
        )
    if existing is not None:
        pending[name_key] = existing
        pending[code_key] = existing
        return existing

    label = DICTIONARY_LABELS.get(model, model.__name__)
    result = _create_or_reuse(model, text=create_name, code=create_code, label=label)
    if result.error or result.item is None:
        raise IntegrityError(result.error or f'Не удалось создать «{create_name}».')
    pending[name_key] = result.item
    pending[code_key] = result.item
    return result.item
