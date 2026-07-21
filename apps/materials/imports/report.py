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
    affected_material_ids: list[str] = field(default_factory=list)
    errors: list[ImportErrorItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str, *, row: int | None = None, column: str | None = None) -> None:
        self.errors.append(ImportErrorItem(row=row, column=column, message=message))

    def summary_lines(self) -> list[str]:
        prefix = 'Будет' if self.dry_run else 'Итого'
        lines = [
            f'{prefix}: материалов создано {self.materials_created}, обновлено {self.materials_updated}',
            f'{prefix}: свойств создано {self.properties_created}, обновлено {self.properties_updated}',
        ]
        if self.tags_merged:
            lines.append(f'{prefix}: материалов с объединением тегов {self.tags_merged}')
        if self.errors:
            lines.append(f'Ошибок: {len(self.errors)}')
        return lines
