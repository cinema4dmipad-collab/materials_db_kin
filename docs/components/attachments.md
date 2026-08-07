# Вложения (attachments)

Файлы можно прикреплять к:

* материалу — вкладка «Файлы»;
* образцу — вкладка «Файлы»;
* скану — подвкладка «Файлы» на карточке скана.

## Хранение

* `file` — оригинал (скачивание всегда отдаёт его);
* `preview_pdf` — PDF для просмотра в браузере;
* `preview_status` — `none` / `skipped` / `pending` / `ready` / `failed`.

| Тип | Превью |
|-----|--------|
| PDF | копия в `preview_pdf` |
| Word (.doc/.docx/.odt/.rtf) | LibreOffice → PDF |
| Excel (.xls/.xlsx/…) | иконка, статус `skipped` |
| прочее | без превью |

Общий слой: `apps/core/attachments/` (`kinds`, `convert`, `processing`).

В Docker установлен `libreoffice-writer-nogui`. Локально: установить LibreOffice или задать `LIBREOFFICE_PATH`.
