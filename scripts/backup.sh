#!/usr/bin/env bash
# §138/§150 — back up Postgres (the source of truth) and the MinIO/S3
# report bucket. Run from the repo root, against a running `docker compose`
# stack:
#
#   ./scripts/backup.sh [backups]
#
# Writes backups/<UTC timestamp>/postgres.dump (pg_dump custom format,
# compressed, restorable with pg_restore — see restore.sh) and
# reports-bucket.tar (the MinIO bucket's contents). This backs up the two
# stores that hold data nothing else can regenerate: Postgres has every
# audit/user/entitlement/purchase row, and the reports bucket has the
# already-rendered PDFs (regenerable from audit data in principle, but not
# automatically, so worth keeping).
#
# A backup nobody has restored is not a backup — see restore.sh and run it
# against a scratch target before trusting either script in production.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_ROOT="${1:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${OUT_ROOT}/${TIMESTAMP}"
mkdir -p "$OUT_DIR"

POSTGRES_USER_VAL="${POSTGRES_USER:-spy}"
POSTGRES_DB_VAL="${POSTGRES_DB:-spy}"
STORAGE_BUCKET_VAL="${STORAGE_BUCKET:-spy-reports}"

echo "==> Backing up Postgres (${POSTGRES_DB_VAL}) to ${OUT_DIR}/postgres.dump"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER_VAL" -d "$POSTGRES_DB_VAL" -F c -f /tmp/spy-backup.dump
docker compose cp postgres:/tmp/spy-backup.dump "${OUT_DIR}/postgres.dump"
docker compose exec -T postgres rm -f /tmp/spy-backup.dump

echo "==> Backing up MinIO bucket (${STORAGE_BUCKET_VAL}) to ${OUT_DIR}/reports-bucket/"
# minio/minio's image has no `tar` (it's a minimal, purpose-built image —
# just the server binary + mc), so mirror into a directory and let
# `docker compose cp` copy that directory recursively instead of archiving
# it first.
docker compose exec -T minio sh -c "
  mc alias set localbackup http://localhost:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null &&
  rm -rf /tmp/spy-backup-bucket && mkdir -p /tmp/spy-backup-bucket &&
  mc mirror --quiet localbackup/${STORAGE_BUCKET_VAL} /tmp/spy-backup-bucket >/dev/null 2>&1 || true
"
docker compose cp minio:/tmp/spy-backup-bucket "${OUT_DIR}/reports-bucket"
docker compose exec -T minio rm -rf /tmp/spy-backup-bucket

du -sh "${OUT_DIR}/postgres.dump" "${OUT_DIR}/reports-bucket"
echo "==> Backup complete: ${OUT_DIR}"
