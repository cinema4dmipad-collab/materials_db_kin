# PostgreSQL backups

Бэкапируется только PostgreSQL. Файлы SeaweedFS / S3 в этот бэкап не входят и должны резервироваться отдельно.

## Создание

- Вручную: запустите создание бэкапа через интерфейс приложения.
- По расписанию: контейнер `backup-cron` раз в минуту вызывает `python manage.py run_scheduled_backup`. Окно запуска — 15 минут после заданного времени (если в эту минуту миграции/БД ещё не готовы, повтор в окне всё ещё сработает). Созданные файлы сохраняются в Docker volume `backups`, смонтированный как `/backups`.
- В образе по умолчанию установлен `postgresql-client-18` (`POSTGRES_CLIENT_MAJOR` в Dockerfile). Версия `pg_dump` должна быть **не ниже** major-версии сервера Postgres (иначе `server version mismatch`).

Проверьте работу планировщика:

```sh
docker compose logs -f backup-cron
docker compose ps backup-cron
```

Для production compose укажите файл явно:

```sh
docker compose -f docker-compose.prod.yml logs -f backup-cron
```

## Восстановление

Остановите запись в приложение, затем восстановите нужный файл в целевую PostgreSQL базу:

```sh
docker compose exec -T backup-cron pg_restore \
  --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
  --dbname="$DB_NAME" --clean --if-exists --no-owner \
  /backups/backup-file.dump
```

Перед восстановлением задайте `PGPASSWORD` либо используйте защищённый `.pgpass`; убедитесь, что имя файла и формат соответствуют созданному бэкапу. При восстановлении в рабочую базу `--clean` удаляет существующие объекты.

`pg_dump` и `pg_restore` доступны в контейнерах, потому что образ приложения устанавливает пакет `postgresql-client`. Каталог `/backups` в образе принадлежит пользователю `appuser`.

Если volume `backups` уже создавался под root и запись падает с Permission denied:

```sh
docker compose run --rm --user root --entrypoint /bin/sh web -c "chown -R appuser:appuser /backups"
```
