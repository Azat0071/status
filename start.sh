#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py seed_default_stores
python manage.py bootstrap_admin
python manage.py collectstatic --noinput

if [ "$(python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'STATUS_PROJECT.settings')
import django
django.setup()
from PRILOJENIA1.models import Product
print('1' if Product.objects.exists() else '0')
PY
)" = "0" ]; then
    python manage.py seed_demo_catalog
fi

exec gunicorn STATUS_PROJECT.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 3
