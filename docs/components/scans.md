# Scans App

Location: `apps/scans/`

**HDF5 ultrasonic scan** files linked to samples.

## Model

**Scan** — sample (FK), title, description, method (echo, shadow, mirror, …), file, tags, upload metadata.

## File Validation

`apps/scans/validators.py`:

* Extensions `.h5`, `.hdf5` only
* HDF5 signature check on upload

Large files supported via streaming storage and extended Gunicorn timeout.

## Public UI

| URL | Action |
|-----|--------|
| `/scans/` | All scans (global list) |
| `/samples/<pk>/scans/` | Scans for one sample |
| Create / detail / delete | Standard CRUD under sample namespace |

Download links use `.file-download-link` with progress indicator (`file_transfer_progress.js`).

## Upload Progress

Multipart uploads with `input[type=file]` go through XHR with `upload.onprogress`; bottom panel shows transfer status.

## Storage

Files stored via default Django storage backend (S3 or local `media/`).

## Tests

`apps/scans/tests.py` — validation, views, file handling.

## Related

Sample attachments (non-HDF5) live in `apps/samples/` attachment views, not in scans app.
