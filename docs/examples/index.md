# Examples

Practical workflows and command examples for Materials DB.

## Table of Contents

- [Create a Material](#create-a-material)
- [Create a Structure Type](#create-a-structure-type)
- [Local Development](local-development.md)
- [Testing](testing.md)
- [Deployment](deployment.md)

## Create a Material

Typical operator workflow:

1. Ensure required **properties** exist in `/properties/`.
2. Ensure **structure type** exists with SQL table created (`/structures/` → manage → Create table).
3. Open `/materials/create/`:
   * Enter code and name
   * Select structure type
   * Add properties via **Добавить** picker
   * Fill structure-specific fields
   * Optionally define composite layers
4. Save → open material detail → **Create sample** if needed.

## Create a Structure Type

Administrator / power user workflow:

1. `/structures/types/create/`
2. Set name, optional manual **SQL table name** (`structures_my_type`), enable layers if needed
3. Add structure fields (from property catalog or custom columns)
4. Save → confirm **Create table** in modal (or later on manage page)
5. Verify badge «Создана в БД» on manage page

Example valid table names:

```
structures_sendvichnaya_panel
structures_ui_custom_name
```

Invalid (rejected by validation):

```
my_table              # missing structures_ prefix
structures_bad-name   # hyphen not allowed
structures_x;drop     # SQL injection attempt
```

## Quick Commands

```powershell
# Migrations
poetry run python manage.py migrate

# Superuser
poetry run python manage.py createsuperuser

# Seed reference data (if available)
poetry run python manage.py seed_data

# Sync all pending structure SQL tables
poetry run python manage.py sync_structure_tables

# Check S3
poetry run python manage.py check_s3_storage
```

## See Also

* [In-app help](/help/) — Russian guide for end users
* [Tasks index](../tasks.md) — documentation by goal
* [Terms](../terms.md) — glossary
