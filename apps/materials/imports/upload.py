from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import UploadedFile

from apps.materials.imports.staging import MATCH_BY_NAME

ALLOWED_SUFFIXES = {'.csv', '.xlsx', '.xlsm'}
SESSION_TEMP_PATH = 'material_import_temp_path'
SESSION_ORIGINAL_NAME = 'material_import_original_name'
SESSION_SHEET = 'material_import_sheet'
SESSION_HEADER_ROW = 'material_import_header_row'
SESSION_GROUP_ROW = 'material_import_group_row'
SESSION_MAPPING = 'material_import_mapping'
SESSION_MODE = 'material_import_mode'
SESSION_MATCH_POLICY = 'material_import_match_policy'
SESSION_DRAFT = 'material_import_draft'
SESSION_STRUCTURE_TYPE_ID = 'material_import_structure_type_id'


def save_uploaded_import_file(uploaded: UploadedFile) -> Path:
    name = Path(uploaded.name or 'import.csv').name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError('Поддерживаются только файлы CSV и XLSX.')

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        for chunk in uploaded.chunks():
            handle.write(chunk)
    finally:
        handle.close()
    return Path(handle.name)


def store_import_session(session, *, temp_path: Path, original_name: str) -> None:
    clear_import_session(session, delete_file=True)
    session[SESSION_TEMP_PATH] = str(temp_path)
    session[SESSION_ORIGINAL_NAME] = original_name
    session[SESSION_MODE] = 'mapped'
    session[SESSION_MATCH_POLICY] = MATCH_BY_NAME
    session.modified = True


def get_import_session_path(session) -> Path | None:
    raw = session.get(SESSION_TEMP_PATH)
    if not raw:
        return None
    path = Path(raw)
    if not path.exists():
        clear_import_session(session, delete_file=False)
        return None
    return path


def get_import_session_name(session) -> str:
    return session.get(SESSION_ORIGINAL_NAME) or 'файл'


def get_import_config(session) -> dict:
    return {
        'sheet': session.get(SESSION_SHEET) or '',
        'header_row': int(session.get(SESSION_HEADER_ROW) or 1),
        'group_row': session.get(SESSION_GROUP_ROW),
        'mapping': session.get(SESSION_MAPPING) or {},
        'mode': session.get(SESSION_MODE) or 'mapped',
        'match_policy': session.get(SESSION_MATCH_POLICY) or MATCH_BY_NAME,
        'draft': session.get(SESSION_DRAFT) or [],
        'structure_type_id': session.get(SESSION_STRUCTURE_TYPE_ID) or '',
    }


def set_import_config(
    session,
    *,
    sheet: str | None = None,
    header_row: int | None = None,
    group_row: int | None = None,
    mapping: dict | None = None,
    mode: str | None = None,
    match_policy: str | None = None,
    draft: list | None = None,
    structure_type_id: str | None = None,
    clear_draft: bool = False,
) -> None:
    if sheet is not None:
        session[SESSION_SHEET] = sheet
    if header_row is not None:
        session[SESSION_HEADER_ROW] = header_row
    if group_row is not None:
        if group_row <= 0:
            session.pop(SESSION_GROUP_ROW, None)
        else:
            session[SESSION_GROUP_ROW] = group_row
    if mapping is not None:
        session[SESSION_MAPPING] = mapping
    if mode is not None:
        session[SESSION_MODE] = mode
    if match_policy is not None:
        session[SESSION_MATCH_POLICY] = match_policy
    if draft is not None:
        session[SESSION_DRAFT] = draft
    if structure_type_id is not None:
        if structure_type_id:
            session[SESSION_STRUCTURE_TYPE_ID] = structure_type_id
        else:
            session.pop(SESSION_STRUCTURE_TYPE_ID, None)
    if clear_draft:
        session.pop(SESSION_DRAFT, None)
    session.modified = True


def clear_import_session(session, *, delete_file: bool = True) -> None:
    from apps.materials.imports.iterate import clear_iterate_session

    raw = session.pop(SESSION_TEMP_PATH, None)
    session.pop(SESSION_ORIGINAL_NAME, None)
    session.pop(SESSION_SHEET, None)
    session.pop(SESSION_HEADER_ROW, None)
    session.pop(SESSION_GROUP_ROW, None)
    session.pop(SESSION_MAPPING, None)
    session.pop(SESSION_MODE, None)
    session.pop(SESSION_MATCH_POLICY, None)
    session.pop(SESSION_DRAFT, None)
    session.pop(SESSION_STRUCTURE_TYPE_ID, None)
    clear_iterate_session(session)
    session.modified = True
    if delete_file and raw:
        try:
            os.unlink(raw)
        except OSError:
            pass
