#!/bin/sh
set -eu

python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application -c /app/gunicorn.conf.py
