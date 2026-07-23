# Materials DB — Documentation

Project documentation for **materials_db_v1** — web database of composite materials, samples, scans, and dynamic structure types.

## Documentation Structure

* [Overview](overview/index.md) — Project purpose, features, system requirements
* [Terms](terms.md) — Domain terminology glossary
* [Tasks](tasks.md) — Task-based index (configuration, development, testing, deployment)
* [Architecture](architecture/index.md) — System architecture, Django apps, data model
  * [Technology Stack](architecture/tech-stack.md) — Technologies and libraries
  * [Testing](architecture/testing.md) — Test suite structure and CI
  * [Export / analytics draft](architecture/analytics-draft.md) — Excel export first; analytics UI deferred (RU)
* [Components](components/index.md) — Main application modules
* [Configuration](configuration/index.md) — Setup and environment variables
  * [Environment Reference](configuration/environment.md) — `.env` variables and deployment profiles
* [Examples](examples/index.md) — Usage and operations examples
  * [Local Development](examples/local-development.md) — Docker Compose, migrations, runserver
  * [Testing](examples/testing.md) — Running tests locally and in CI
  * [Deployment](examples/deployment.md) — Dokploy, production compose

## User-Facing Help

In-app help page (Russian): `/help/` — [`templates/core/help.html`](../templates/core/help.html).

## Documentation Format

* **Markdown files** (`docs/`) — for reading in the repository and on GitLab
* Source code and templates remain the authoritative reference for UI behaviour
