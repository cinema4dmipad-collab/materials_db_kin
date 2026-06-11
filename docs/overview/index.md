# Overview

**Materials DB** (materials_db_v1) is a Django web application for storing and managing data on composite materials used in laser ultrasonic and related NDT workflows at KeenetiCA.

## Project Description

The system combines a relational catalog (materials, samples, properties, tags) with **dynamic structure types**: each structure type can define its own set of fields and a dedicated SQL table for construction parameters (sandwich panels, monoliths, links to other materials, and so on).

Files (HDF5 scans, photos, reports) are stored in S3-compatible object storage or locally, depending on configuration.

## Key Features

* **Materials catalog** — codes, names, structure types, property values, composite layer stacks
* **Reference properties** — shared dictionary of measurable parameters (density, modulus, etc.)
* **Dynamic structure types** — admin-configurable fields with SQL-backed instance tables
* **Samples** — physical specimens linked to materials, with sample-specific property overrides
* **Scans** — HDF5 ultrasonic scan files attached to samples
* **Attachments** — generic files on materials and samples
* **Tags** — cross-entity labels with list filtering
* **Search and filters** — unified filter bar on list and detail pages
* **Public UI + Django admin** — operator-facing site and admin for advanced configuration

## Data Model (High Level)

```
Reference Property ──┐
                     ├── Material ── Sample ── Scan (HDF5)
Structure Type ──────┤              └── Attachment
  └── SQL table rows ┘
Composite layers (optional, per material)
```

Recommended data entry order: **properties → structure type (with SQL table) → material → sample → scans/files**.

## System Requirements

* **Python**: 3.13+
* **Database**: PostgreSQL 16 (production); SQLite supported for quick local tests without `DB_ENGINE=postgresql`
* **Object storage**: S3-compatible (SeaweedFS in Docker Compose) or local `media/`
* **Dependencies**: see [`pyproject.toml`](../../pyproject.toml)

## Architecture Overview

Django monolith with apps under `apps/`, server-rendered templates, Bootstrap 5 UI, and dynamic SQL tables managed by `apps.structures`. See [Architecture](../architecture/index.md) for module layout and design decisions.

## Deployment

* **Local / dev**: `docker compose up` — Postgres, SeaweedFS, web, nginx
* **Production**: Dokploy + `docker-compose.prod.yml` — build and deploy handled outside GitLab CI
* **CI**: GitLab pipeline runs tests only (see [Testing](../architecture/testing.md))
