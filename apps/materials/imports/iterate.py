from __future__ import annotations

from apps.materials.imports.staging import DraftMaterial

SESSION_ITERATE_ACTIVE = 'material_import_iterate_active'
SESSION_ITERATE_INDEX = 'material_import_iterate_index'
SESSION_ITERATE_LOG = 'material_import_iterate_log'
SESSION_ITERATE_IDS = 'material_import_iterate_ids'
SESSION_ITERATE_TOTAL = 'material_import_iterate_total'


def clear_iterate_session(session) -> None:
    session.pop(SESSION_ITERATE_ACTIVE, None)
    session.pop(SESSION_ITERATE_INDEX, None)
    session.pop(SESSION_ITERATE_LOG, None)
    session.pop(SESSION_ITERATE_IDS, None)
    session.pop(SESSION_ITERATE_TOTAL, None)
    session.modified = True


def is_iterate_active(session) -> bool:
    return bool(session.get(SESSION_ITERATE_ACTIVE))


def start_iterate(session, drafts: list[DraftMaterial]) -> int | None:
    """Начинает построчный режим. Возвращает индекс первой активной строки или None."""
    index = next_active_index(drafts, start_at=0)
    total = count_active_drafts(drafts)
    session[SESSION_ITERATE_ACTIVE] = True
    session[SESSION_ITERATE_LOG] = []
    session[SESSION_ITERATE_IDS] = []
    session[SESSION_ITERATE_TOTAL] = total
    if index is None:
        session.pop(SESSION_ITERATE_INDEX, None)
    else:
        session[SESSION_ITERATE_INDEX] = index
    session.modified = True
    return index


def get_iterate_total(session) -> int:
    try:
        return max(0, int(session.get(SESSION_ITERATE_TOTAL) or 0))
    except (TypeError, ValueError):
        return 0


def get_iterate_index(session) -> int | None:
    raw = session.get(SESSION_ITERATE_INDEX)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_iterate_log(session) -> list[dict]:
    return list(session.get(SESSION_ITERATE_LOG) or [])


def get_iterate_material_ids(session) -> list[str]:
    return [str(item) for item in (session.get(SESSION_ITERATE_IDS) or [])]


def append_iterate_log(session, entry: dict) -> None:
    log = get_iterate_log(session)
    log.append(entry)
    session[SESSION_ITERATE_LOG] = log
    session.modified = True


def append_iterate_material_ids(session, material_ids: list[str]) -> None:
    if not material_ids:
        return
    ids = get_iterate_material_ids(session)
    for material_id in material_ids:
        if material_id not in ids:
            ids.append(material_id)
    session[SESSION_ITERATE_IDS] = ids
    session.modified = True


def set_iterate_index(session, index: int | None) -> None:
    if index is None:
        session.pop(SESSION_ITERATE_INDEX, None)
    else:
        session[SESSION_ITERATE_INDEX] = index
    session.modified = True


def next_active_index(drafts: list[DraftMaterial], *, start_at: int) -> int | None:
    for index in range(max(0, start_at), len(drafts)):
        draft = drafts[index]
        if draft.action != 'skip':
            return index
    return None


def count_active_drafts(drafts: list[DraftMaterial]) -> int:
    return sum(1 for draft in drafts if draft.action != 'skip')


def iterate_progress(session, drafts: list[DraftMaterial]) -> tuple[int, int, int, int]:
    """
    Прогресс построчного режима относительно стартового числа строк.
    Возвращает (position_1based, total, done, percent).
    """
    total = get_iterate_total(session) or count_active_drafts(drafts)
    remaining = count_active_drafts(drafts)
    done = max(0, total - remaining)
    position = min(done + 1, total) if total else 0
    percent = int(round(100.0 * done / total)) if total else 0
    return position, total, done, percent


def apply_iterate_row_post(draft: DraftMaterial, post) -> DraftMaterial:
    """Обновляет название, код и include текущей строки из формы построчного шага."""
    if 'name' in post:
        draft.name = (post.get('name') or '').strip()
    if 'code' in post:
        draft.code = (post.get('code') or '').strip()
    for p_index, prop in enumerate(draft.properties):
        prop.include = post.get(f'include_{p_index}') == '1'
    for s_index, struct_val in enumerate(draft.structure_values):
        struct_val.include = post.get(f'include_struct_{s_index}') == '1'
    return draft
