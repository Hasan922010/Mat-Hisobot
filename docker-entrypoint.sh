#!/usr/bin/env bash
set -euo pipefail

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput

  if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username,
        os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
        os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
    print(f'Superuser yaratildi: {username}')
"
  fi
fi

exec "$@"
