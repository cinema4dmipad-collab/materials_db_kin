# Changelog

Все заметные изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Added

- Модуль сканов и образцов с хранением файлов в S3 (SeaweedFS).
- Динамические таблицы структур материалов (SQL + админка Django).
- Связи материалов со слоями и структурными таблицами.
- Теги, фильтры и поиск в интерфейсе списков.
- FAQ-раздел.
- Логотип и обновлённая Bootstrap-вёрстка.
- Production Docker Compose для Dokploy (`docker-compose.prod.yml`).
- GitLab CI/CD: тесты, сборка образа, manual deploy staging/production.
- Compose для S3-хранилища (`docker-compose.storage.yml`).

### Changed

- Рефакторинг моделей структур: удалены legacy EAV-модели, улучшены формы.
- Упрощён prod compose под Dokploy (образы через `WEB_IMAGE` / `NGINX_IMAGE`, без build на сервере).
- Обновлены цвета и стили UI.

### Fixed

- Восстановлена установка зависимостей через Poetry в Dockerfile.
- Сборка web-образа из Dockerfile, когда `WEB_IMAGE` не задан.
- Пропуск docker build при redeploy в Dokploy.
- Подключение SeaweedFS к `dokploy-network` для доступа Django к S3.

### Security

- Безопасная конфигурация через переменные окружения (`SECRET_KEY` обязателен при `DEBUG=False`).
