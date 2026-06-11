# Task-Based Index

Task-oriented index with direct links to documentation sections.

## Configuration

- [Environment variables](configuration/environment.md) — `.env`, `.env.prod.example`, S3, database
- [Configuration overview](configuration/index.md) — local Docker, production, storage profile
- [Django settings](configuration/index.md#django-settings) — `config/settings.py` behaviour

## Development

- [Local development setup](examples/local-development.md) — Poetry, Docker Compose, migrations
- [Structure type with SQL table](components/structures.md) — create type, validate table name, create table
- [Reference properties](components/references.md) — property catalog and picker integration
- [Material form](components/materials.md) — properties, layers, structure fields
- [List filters](components/core.md) — server-side and client-side filtering

## Testing

- [Run tests](examples/testing.md) — `manage.py test`, CI pipeline
- [Test architecture](architecture/testing.md) — app test modules, SQLite vs PostgreSQL

## Deployment

- [Dokploy deployment](examples/deployment.md) — `docker-compose.prod.yml`, env on server
- [S3 / storage service](configuration/environment.md#s3--object-storage) — separate SeaweedFS compose
- [CI pipeline](architecture/tech-stack.md#cicd) — GitLab test stage only

## Operations

- [Create material workflow](examples/index.md#create-a-material) — end-to-end operator path
- [Upload HDF5 scan](components/scans.md) — validation, progress bar
- [Sync structure tables](components/structures.md#management-commands) — `sync_structure_tables` command
- [In-app help](/help/) — Russian user guide in the web UI
