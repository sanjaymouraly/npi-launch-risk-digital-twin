#!/bin/bash
set -e
mkdir -p backups
echo "Backing up SQLite..."
cp backend/npi.db backups/npi_$(date +%F).db 2>/dev/null || echo "No npi.db yet"
echo "Backing up exports..."
curl -s http://localhost:8000/api/projects/ | python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join([p['id'] for p in d]))" | while read pid; do
  curl -s http://localhost:8000/api/projects/$pid/export > backups/export_${pid}_$(date +%F).json
  echo "Exported $pid"
done
echo "Backup complete: $(ls -lh backups/)"
