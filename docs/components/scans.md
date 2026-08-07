# Scans App

Location: `apps/scans/`

**HDF5 ultrasonic scan** files linked to samples.

## Model

**Scan** — sample (FK), title, description, method (echo, shadow, immersion, …), HDF5 `file`, optional `preview` (PNG/JPEG/WebP C-scan thumbnail), tags, upload metadata. Document attachments: `ScanAttachment` (see [attachments.md](attachments.md)).

## File Validation

`apps/scans/validators.py`:

* Extensions `.h5`, `.hdf5` only
* HDF5 signature check on upload
* Optional preview: `.png` / `.jpg` / `.jpeg` / `.webp`, max 5 MB, image magic check

Large HDF5 files supported via streaming storage and extended Gunicorn timeout. Preview is a separate small file (not extracted from HDF5).

## Public UI

| URL | Action |
|-----|--------|
| `/scans/` | All scans (global list, tile grid) |
| `/samples/<pk>/scans/` | Scans for one sample (tile grid) |
| Create / detail / delete | Standard CRUD under sample namespace |
| `…/scans/<pk>/attachments/` | Document attachments for a scan |
| `…/scans/<pk>/tags/` | POST — save tags from detail card (when scan’s workspace is active) |

Tag forms use `sample.workspace` / `scan.workspace` for suggestions and assignment (not the viewer’s active workspace when the sample is visible via a shared material).

Download links use `.file-download-link` with progress indicator (`file_transfer_progress.js`).

**Открыть в KeenetiX** — desktop channel (`POST /api/v1/desktop/open-scan/`); кнопка на карточке и в списках.
API create: multipart `file` + optional `preview`; response includes `preview_url` when set.
API update: `PUT /api/v1/scans/{id}/` replaces HDF5 (+ optional preview) — KeenetiX «Обновить скан».
Preview is served via app proxy (`GET …/preview/`), not a direct S3 URL (SeaweedFS is often unreachable from the browser).

## Upload Progress

Multipart uploads with `input[type=file]` go through XHR with `upload.onprogress`; bottom panel shows transfer status.

## Storage

Files stored via default Django storage backend (S3 or local `media/`).

## Tests

`apps/scans/tests.py` — validation, views, file handling.

## Related

Sample attachments (non-HDF5) live in `apps/samples/` attachment views, not in scans app.
