from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportErrorItem:
    row: int | None
    column: str | None
    message: str


@dataclass
class ImportReport:
    dry_run: bool = False
    materials_created: int = 0
    materials_updated: int = 0
    properties_created: int = 0
    properties_updated: int = 0
    tags_merged: int = 0
    dictionaries_created: list[str] = field(default_factory=list)
    dictionaries_linked_by_code: list[str] = field(default_factory=list)
    affected_material_ids: list[str] = field(default_factory=list)
    errors: list[ImportErrorItem] = field(default_factory=list)
    entity_noun: str = 'материалов'

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str, *, row: int | None = None, column: str | None = None) -> None:
        self.errors.append(ImportErrorItem(row=row, column=column, message=message))

    def add_dictionary_created(self, label: str, name: str, code: str) -> None:
        entry = f'{label}: «{name}» (код {code})'
        if entry not in self.dictionaries_created:
            self.dictionaries_created.append(entry)

    def add_dictionary_linked_by_code(self, label: str, raw: str, existing_name: str, code: str) -> None:
        entry = f'{label}: «{raw}» → существующее «{existing_name}» (код {code})'
        if entry not in self.dictionaries_linked_by_code:
            self.dictionaries_linked_by_code.append(entry)

    def summary_lines(self) -> list[str]:
        prefix = 'Будет' if self.dry_run else 'Итого'
        lines = [
            f'{prefix}: {self.entity_noun} создано {self.materials_created}, обновлено {self.materials_updated}',
            f'{prefix}: свойств создано {self.properties_created}, обновлено {self.properties_updated}',
        ]
        if self.tags_merged:
            lines.append(f'{prefix}: записей с объединением тегов {self.tags_merged}')
        if self.dictionaries_created:
            lines.append(
                f'{prefix}: значений справочников создано — {len(self.dictionaries_created)}'
            )
            lines.extend(f'  · {item}' for item in self.dictionaries_created[:20])
            if len(self.dictionaries_created) > 20:
                lines.append(f'  · … ещё {len(self.dictionaries_created) - 20}')
        if self.dictionaries_linked_by_code:
            lines.append(
                f'{prefix}: сопоставлено с существующими по коду — '
                f'{len(self.dictionaries_linked_by_code)}'
            )
            lines.extend(f'  · {item}' for item in self.dictionaries_linked_by_code[:10])
            if len(self.dictionaries_linked_by_code) > 10:
                lines.append(f'  · … ещё {len(self.dictionaries_linked_by_code) - 10}')
        if self.errors:
            lines.append(f'Ошибок: {len(self.errors)}')
        return lines
