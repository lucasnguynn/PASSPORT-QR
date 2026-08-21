#!/usr/bin/env bash
# Run daily via cron: 0 2 * * * /app/scripts/backup.sh
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${BACKUP_DIR:=/backups}"
: "${MINIO_ALIAS:=minio}"

timestamp="$(date -u +%Y%m%d_%H%M%S)"
backup_file="${BACKUP_DIR}/db_${timestamp}.sql.gz"
mkdir -p "${BACKUP_DIR}"

docker exec dpp-postgres pg_dump --no-password --format=plain \
  --username "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip -9 > "${backup_file}"
mc cp "${backup_file}" "${MINIO_ALIAS}/backups/db/"

mapfile -t expired < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'db_*.sql.gz' -printf '%T@ %p\n' \
  | sort -rn | tail -n +31 | cut -d' ' -f2-)
if ((${#expired[@]})); then
  rm -f -- "${expired[@]}"
fi
