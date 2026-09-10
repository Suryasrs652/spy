#!/usr/bin/env bash
# §138/§150 — restore a backup made by backup.sh. Run from the repo root,
# against a running `docker compose` stack:
#
#   ./scripts/restore.sh backups/20260910T120000Z [target_db] [target_bucket]
#
# target_db defaults to spy_restore_test — a SEPARATE database created for
# this restore, never the live `spy` database — precisely so this script is
# safe to run as a drill against production-adjacent environments without
# risking the data it's supposed to be protecting. Pass the live DB name
# explicitly (and mean it) for a real disaster-recovery restore.
set -euo pipefail

BACKUP_DIR="${1:?Usage: restore.sh <backup_dir> [target_db] [target_bucket]}"
TARGET_DB="${2:-spy_restore_test}"
TARGET_BUCKET="${3:-spy-reports-restore-test}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

POSTGRES_USER_VAL="${POSTGRES_USER:-spy}"

if [ ! -f "${BACKUP_DIR}/postgres.dump" ]; then
  echo "No postgres.dump found in ${BACKUP_DIR}" >&2
  exit 1
fi

echo "==> Restoring Postgres dump into database '${TARGET_DB}'"
docker compose exec -T postgres psql -U "$POSTGRES_USER_VAL" -d postgres -c \
  "DROP DATABASE IF EXISTS ${TARGET_DB};" >/dev/null
docker compose exec -T postgres psql -U "$POSTGRES_USER_VAL" -d postgres -c \
  "CREATE DATABASE ${TARGET_DB};" >/dev/null

docker compose cp "${BACKUP_DIR}/postgres.dump" postgres:/tmp/spy-restore.dump
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER_VAL" -d "$TARGET_DB" --no-owner --no-privileges /tmp/spy-restore.dump
docker compose exec -T postgres rm -f /tmp/spy-restore.dump

ROW_COUNTS=$(docker compose exec -T postgres psql -U "$POSTGRES_USER_VAL" -d "$TARGET_DB" -t -c "
  SELECT 'users=' || (SELECT count(*) FROM users)
    || ' organizations=' || (SELECT count(*) FROM organizations)
    || ' audits=' || (SELECT count(*) FROM audits);
")
echo "==> Postgres restored into '${TARGET_DB}': ${ROW_COUNTS}"

if [ -d "${BACKUP_DIR}/reports-bucket" ]; then
  echo "==> Restoring MinIO bucket into '${TARGET_BUCKET}'"
  docker compose exec -T minio rm -rf /tmp/spy-restore-bucket
  docker compose cp "${BACKUP_DIR}/reports-bucket" minio:/tmp/spy-restore-bucket
  docker compose exec -T minio sh -c "
    mc alias set localrestore http://localhost:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null &&
    mc mb --ignore-existing localrestore/${TARGET_BUCKET} &&
    mc mirror --quiet /tmp/spy-restore-bucket localrestore/${TARGET_BUCKET} >/dev/null 2>&1 &&
    rm -rf /tmp/spy-restore-bucket
  "
  OBJECT_COUNT=$(docker compose exec -T minio sh -c "mc ls localrestore/${TARGET_BUCKET} --recursive 2>/dev/null | wc -l")
  echo "==> MinIO bucket '${TARGET_BUCKET}' restored: ${OBJECT_COUNT} object(s)"
fi

echo "==> Restore complete. Verify the data, then drop the scratch database/bucket:"
echo "    docker compose exec postgres psql -U ${POSTGRES_USER_VAL} -d postgres -c 'DROP DATABASE ${TARGET_DB};'"
echo "    docker compose exec minio mc rb --force localrestore/${TARGET_BUCKET}"
