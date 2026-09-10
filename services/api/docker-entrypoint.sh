#!/usr/bin/env bash
set -euo pipefail

RUN_MODE="${RUN_MODE:-api}"

wait_for_db() {
  echo "Waiting for database migrations to be applicable..."
  python -c "
import time, sys
import psycopg
from app.core.config import get_settings

settings = get_settings()
# psycopg.connect() wants a bare 'postgresql://' URI/libpq keyword string,
# not the 'postgresql+psycopg://' SQLAlchemy dialect+driver form.
dsn = settings.database_url_sync.replace('postgresql+psycopg://', 'postgresql://', 1)
for _ in range(30):
    try:
        conn = psycopg.connect(dsn)
        conn.close()
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f'db not ready yet: {exc}')
        time.sleep(2)
sys.exit(1)
"
}

case "$RUN_MODE" in
  api)
    wait_for_db
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ;;
  worker)
    wait_for_db
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 -Q audit.high,audit.standard,crawl,analysis,gsc,reports,backlinks,maintenance
    ;;
  beat)
    wait_for_db
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  *)
    echo "Unknown RUN_MODE: $RUN_MODE" >&2
    exit 1
    ;;
esac
