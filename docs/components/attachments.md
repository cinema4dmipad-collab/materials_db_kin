# Вложения (attachments)

Файлы можно прикреплять к:

* материалу — вкладка «Файлы»;
* образцу — вкладка «Файлы»;
* скану — подвкладка «Файлы» на карточке скана.

## Хранение

* `file` — оригинал (скачивание всегда отдаёт его);
* `preview_image` — PNG-миниатюра первой страницы для списка;
* `preview_status` — `none` / `skipped` / `pending` / `ready` / `failed`.

| Тип | Превью |
|-----|--------|
| PDF | первая страница → PNG |
| Word (.doc/.docx/.odt/.rtf) | LibreOffice → PDF → первая страница → PNG |
| PPTX (.ppt/.pptx/.odp) | LibreOffice Impress → PDF → первая страница → PNG |
| Excel (.xls/.xlsx/…) | иконка, статус `skipped` |
| прочее | без превью |

Полный документ для просмотра не хранится — в UI только миниатюра на плитке (сетка как Google Drive: название, превью, автор, дата; действия в меню ⋮).

Добавление файла — отдельная форма (кнопка **«Добавить»** в шапке вкладки «Файлы»), не inline под списком.

Общий слой: `apps/core/attachments/` (`kinds`, `convert`, `thumbnail`, `processing`).

В Docker: `libreoffice-writer-nogui` и `libreoffice-impress-nogui`. Рендер PDF: `pypdfium2` + Pillow. Локально: LibreOffice или `LIBREOFFICE_PATH`.
