#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn STATUS_PROJECT.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 3
