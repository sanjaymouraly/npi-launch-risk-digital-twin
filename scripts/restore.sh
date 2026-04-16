#!/bin/bash
# Restore a SQLite backup produced by scripts/backup.sh
#   ./scripts/restore.sh backups/npi_2026-10-21.db
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 backups/npi_YYYY-MM-DD.db"
  exit 1
fi

if [ ! -f "$1" ]; then
  echo "Backup not found: $1"
  exit 1
fi

cp "$1" backend/npi.db
rm -f backend/npi.db-wal backend/npi.db-shm
echo "Restored backend/npi.db from $1"
echo "Restart the API and verify: curl http://127.0.0.1:8000/api/ready"
