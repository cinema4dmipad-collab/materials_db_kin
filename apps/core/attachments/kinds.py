from __future__ import annotations

import os

KIND_PDF = 'pdf'
KIND_WORD = 'word'
KIND_EXCEL = 'excel'
KIND_OTHER = 'other'

WORD_EXTENSIONS = {'.doc', '.docx', '.odt', '.rtf'}
EXCEL_EXTENSIONS = {'.xls', '.xlsx', '.xlsm', '.ods'}
PDF_EXTENSIONS = {'.pdf'}

KIND_LABELS = {
    KIND_PDF: 'PDF',
    KIND_WORD: 'Word',
    KIND_EXCEL: 'Excel',
    KIND_OTHER: 'Файл',
}


def detect_attachment_kind(filename: str) -> str:
    extension = os.path.splitext(filename or '')[1].lower()
    if extension in PDF_EXTENSIONS:
        return KIND_PDF
    if extension in WORD_EXTENSIONS:
        return KIND_WORD
    if extension in EXCEL_EXTENSIONS:
        return KIND_EXCEL
    return KIND_OTHER
