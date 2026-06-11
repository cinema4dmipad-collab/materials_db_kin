# Domain Terminology

Glossary of terms used in Materials DB and related composite / NDT workflows.

## Catalog Entities

| Term | Description |
|------|-------------|
| **Material** | Card for a composite or prepreg system: code, name, structure type, properties, optional layer stack. |
| **Sample** | Physical specimen (plate, part, control element) made from a material; may override property values. |
| **Property** | Entry in the reference catalog: name, code, unit, data type (number, string, boolean, date). |
| **Property group** | Optional grouping of properties in the reference catalog (admin). |
| **Tag** | Normalized label attached to materials, samples, or scans; used for filtering. |

## Structure Types

| Term | Description |
|------|-------------|
| **Structure type** | Template defining extra fields for materials of that class (e.g. sandwich panel). |
| **Structure field** | Column definition within a type: label, SQL column name, field type, defaults. |
| **Structure instance / record** | Row in the type's SQL table linked to material parameters. |
| **SQL table name** | Physical PostgreSQL table for a type; must start with `structures_`, snake_case, unique. |
| **Material link field** | Field type referencing another material in the same database. |
| **Allow layers** | Flag on structure type enabling composite layer table on material form. |

## Composite Layers

| Term | Description |
|------|-------------|
| **Composite layer** | Single ply in a material stack: layer material, reinforcement angle, thickness (mm). |
| **Layer diagram** | Visual stack summary on material detail page. |

## Scans and Files

| Term | Description |
|------|-------------|
| **Scan** | HDF5 ultrasonic data file (`.h5`, `.hdf5`) linked to a sample. |
| **Scan method** | Control mode: echo, shadow, mirror, etc. |
| **Attachment** | Non-HDF5 file (photo, PDF) on material or sample. |

## Technical

| Term | Description |
|------|-------------|
| **ORM metadata** | Django models for types, fields, materials — stored in default DB. |
| **Dynamic SQL table** | Per-type PostgreSQL table created by `SQLExecutor`; not a Django model. |
| **Dokploy** | Deployment platform used for production build and run. |
| **SeaweedFS** | S3-compatible storage used in local Docker Compose and production. |
