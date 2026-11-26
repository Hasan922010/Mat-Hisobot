#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

PG_BIN="/usr/lib/postgresql/18/bin"
PG_DATA=".pgdata"
PG_SOCK="/tmp/pgsock"
PG_PORT="5433"

mkdir -p "$PG_SOCK"

if [ ! -d "$PG_DATA" ]; then
  echo ">>> PostgreSQL klasteri yaratilmoqda ($PG_DATA)..."
  "$PG_BIN/initdb" -D "$PG_DATA" -U postgres --auth=trust -E UTF8 --locale=C.UTF-8
fi

if ! pg_isready -h "$PG_SOCK" -p "$PG_PORT" >/dev/null 2>&1; then
  echo ">>> PostgreSQL 18 ishga tushirilmoqda ($PG_SOCK:$PG_PORT)..."
  "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_DATA/logfile" -o "-h '' -k $PG_SOCK -p $PG_PORT" start
  psql -h "$PG_SOCK" -p "$PG_PORT" -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'mat_hisobot'" | grep -q 1 \
    || psql -h "$PG_SOCK" -p "$PG_PORT" -U postgres -c "CREATE DATABASE mat_hisobot;"
fi

echo ">>> Migratsiyalar tekshirilmoqda..."
uv run python manage.py migrate --noinput

QCLUSTER_PID=""
cleanup() {
  echo ""
  echo ">>> To'xtatilmoqda..."
  if [ -n "$QCLUSTER_PID" ] && kill -0 "$QCLUSTER_PID" 2>/dev/null; then
    pkill -P "$QCLUSTER_PID" 2>/dev/null || true
    kill "$QCLUSTER_PID" 2>/dev/null || true
    wait "$QCLUSTER_PID" 2>/dev/null || true
  fi
  pkill -f "manage.py qcluster" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Eski qolib ketgan qcluster worker'larni tozalash (eski kod bilan ishlashining oldini oladi)
pkill -f "manage.py qcluster" 2>/dev/null || true

echo ">>> Django-Q2 worker (qcluster) fonda ishga tushirilmoqda..."
uv run python manage.py qcluster &
QCLUSTER_PID=$!

PORT="${1:-}"
if [ -z "$PORT" ]; then
  PORT=$(uv run python -c "
import socket
for p in range(8000, 8020):
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', p)) != 0:
            print(p)
            break
")
fi

echo ">>> Server tayyor: http://127.0.0.1:$PORT"
uv run python manage.py runserver "127.0.0.1:$PORT"
