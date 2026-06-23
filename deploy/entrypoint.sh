#!/bin/sh
set -eu

if [ ! -s /app/BUILD_COMMIT ]; then
  echo "WARN: /app/BUILD_COMMIT missing — Git commit will not show on /debug/ (rebuild web image; see deploy/DOKPLOY.md)" >&2
fi

python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application -c /app/gunicorn.conf.py
