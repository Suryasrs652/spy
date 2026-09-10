# Backup and restore (§138/§150)

```bash
./scripts/backup.sh                                    # -> backups/<UTC timestamp>/
./scripts/restore.sh backups/<timestamp>                # restores into scratch spy_restore_test / spy-reports-restore-test
./scripts/restore.sh backups/<timestamp> spy spy-reports  # a REAL restore over the live DB/bucket — only ever do this deliberately
```

Both scripts run against a live `docker compose` stack (they shell out to
`docker compose exec`/`docker compose cp`) and back up the two stores that
hold data nothing else can regenerate:

- **Postgres** (`pg_dump -F c`, restorable with `pg_restore`) — every user,
  organization, audit, entitlement, and purchase row.
- **The MinIO/S3 report bucket** — already-rendered PDF reports. In
  principle these are regenerable from audit data, but not automatically,
  so they're backed up too.

`restore.sh` defaults to a **separate** scratch database
(`spy_restore_test`) and bucket (`spy-reports-restore-test`) rather than the
live ones — the whole point is that this script is safe to run as a drill
at any time, on any environment, without risking the data it exists to
protect. Pass the live database/bucket name explicitly only when you mean
to actually restore over production, e.g. during a real incident.

## Verified

On 2026-09-10, a full cycle was run against the local dev stack: backed up
1185 users / 1185 organizations / 391 audits and 114 report PDFs, restored
into scratch targets, and confirmed byte-for-byte: a specific user row's
`(id, email, created_at)` matched exactly, and a specific PDF's SHA-256
matched exactly, between the live and restored copies. An untested backup
is not a backup — this is what makes these two scripts one.

## What this doesn't cover

This is a manual/cron-adaptable pair of scripts, not a scheduled job wired
into the app itself — deliberately. In a real deployment, backup scheduling
belongs to whatever already owns durability there (a managed Postgres
service's automated snapshots/point-in-time recovery, a Kubernetes
CronJob, a scheduled CI workflow), not to this application's own Celery
Beat (which already runs the §109 retention job, a different concern:
deleting data on purpose, not protecting against losing it by accident).
