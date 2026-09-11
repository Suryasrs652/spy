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
    # --reload (dev-only file-watching) would just add overhead in
    # production, where the image is rebuilt for every deploy anyway.
    if [ "${ENVIRONMENT:-development}" = "production" ]; then
      exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    else
      exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    fi
    ;;
  worker)
    wait_for_db
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 -Q audit.high,audit.standard,crawl,analysis,gsc,reports,backlinks,maintenance
    ;;
  beat)
    wait_for_db
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  worker_and_beat)
    # Single-container fallback for small deployments that can't run worker
    # and beat as separate services (e.g. a platform's free-tier service
    # cap) — beat backgrounded, worker in the foreground as PID 1 so the
    # container's restart policy tracks the worker. Never run this
    # alongside a standalone `beat` mode process: exactly one beat process
    # must exist at a time, or every scheduled task double-fires.
    wait_for_db
    celery -A app.workers.celery_app beat --loglevel=info &
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 -Q audit.high,audit.standard,crawl,analysis,gsc,reports,backlinks,maintenance
    ;;
  *)
    echo "Unknown RUN_MODE: $RUN_MODE" >&2
    exit 1
    ;;
esac
