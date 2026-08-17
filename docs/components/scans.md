# Scans App

Location: `apps/scans/`

**HDF5 ultrasonic scan** files linked to samples.

## Model

**Scan** — sample (FK), title, description, method (echo, shadow, immersion, …), HDF5 `file`, optional previews `preview` (C-scan), `preview_b_xz`, `preview_b_yz` (PNG/JPEG/WebP), tags, upload metadata. Document attachments: `ScanAttachment` (see [attachments.md](attachments.md)).

## File Validation

`apps/scans/validators.py`:

* Extensions `.h5`, `.hdf5` only
* HDF5 signature check on upload
* Optional previews (C-scan, B-scan XZ, B-scan YZ): `.png` / `.jpg` / `.jpeg` / `.webp`, max 5 MB, image magic check

Large HDF5 files supported via streaming storage and extended Gunicorn timeout. Preview is a separate small file (not extracted from HDF5).

## Public UI

| URL | Action |
|-----|--------|
| `/scans/` | All scans (global list, tile grid) |
| `/samples/<pk>/scans/` | Scans for one sample (tile grid); **Добавить** opens a separate create form |
| `/samples/<pk>/scans/create/` | Upload HDF5 + title/method/previews |
| `/samples/<pk>/scans/<pk>/` | Detail / edit / delete under sample namespace |
| `…/scans/<pk>/attachments/` | Document attachments for a scan |
| `…/scans/<pk>/tags/` | POST — save tags from detail card (when scan’s workspace is active) |

Tag forms use `sample.workspace` / `scan.workspace` for suggestions and assignment (not the viewer’s active workspace when the sample is visible via a shared material).

Download links use `.file-download-link` with progress indicator (`file_transfer_progress.js`).

**Открыть в KeenetiX** — desktop channel (`POST /api/v1/desktop/open-scan/`); кнопка на карточке и в списках.
API create: multipart `file` + optional `preview` (C), `preview_b_xz`, `preview_b_yz`; `title` / `method` / `description` задаются в том же POST до записи в БД. `GET /api/v1/scans/options/` — список методов и полей превью для диалога KeenetiX.
API update: `PUT /api/v1/scans/{id}/` replaces HDF5 (+ optional previews) — KeenetiX «Обновить скан».
Previews are served via app proxy (`GET …/preview/` for C-scan, `GET …/preview/b-xz/` and `…/preview/b-yz/`), not a direct S3 URL (SeaweedFS is often unreachable from the browser).
List and detail UI: arrows under the thumbnail cycle **B-скан-XZ → B-скан-YZ → C-скан**.

## Upload Progress

Multipart uploads with `input[type=file]` go through XHR with `upload.onprogress`; bottom panel shows transfer status.

## Storage

Files stored via default Django storage backend (S3 or local `media/`).

## Tests

`apps/scans/tests.py` — validation, views, file handling.

## Related

Sample attachments (non-HDF5) live in `apps/samples/` attachment views, not in scans app.
