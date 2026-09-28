#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
SERVICE="${SERVICE:-alert-bot}"
DB_PATH_IN_CONTAINER="${DB_PATH_IN_CONTAINER:-/data/listings.db}"

mkdir -p "${BACKUP_DIR}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${BACKUP_DIR}/listings-${STAMP}.db.gz"

cd "${PROJECT_DIR}"

docker compose exec -T "${SERVICE}" python - "${DB_PATH_IN_CONTAINER}" <<'PYEOF' | gzip > "${ARCHIVE}"
import sqlite3
import sys
import tempfile
from pathlib import Path

source_path = sys.argv[1]
with tempfile.TemporaryDirectory() as workspace:
    snapshot_path = Path(workspace) / "snapshot.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(snapshot_path) as snapshot:
        source.backup(snapshot)
    sys.stdout.buffer.write(snapshot_path.read_bytes())
PYEOF

if [[ ! -s "${ARCHIVE}" ]]; then
  echo "$(date -u +%FT%TZ) backup FAILED: empty archive ${ARCHIVE}" >&2
  rm -f "${ARCHIVE}"
  exit 1
fi

find "${BACKUP_DIR}" -name 'listings-*.db.gz' -mtime "+${RETAIN_DAYS}" -delete

echo "$(date -u +%FT%TZ) backup ok $(du -h "${ARCHIVE}" | cut -f1) ${ARCHIVE}"
