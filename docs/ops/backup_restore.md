# Backup and restore

Simulation runs, optimisation results, scenario definitions and the audit trail are
business records: they are the evidence behind a launch decision. Back them up.

---

## PostgreSQL (production)

### Backup

```bash
# Full logical backup (custom format, supports parallel restore)
pg_dump -Fc -h db-host -U npi -d npi -f npi-$(date +%F-%H%M).dump

# Plain SQL, easier to inspect
pg_dump -h db-host -U npi -d npi > npi-$(date +%F-%H%M).sql
```

For a large database, snapshot the volume instead and take a logical dump only for
logical integrity.

### Restore

```bash
createdb -h db-host -U npi npi_restored
pg_restore -h db-host -U npi -d npi_restored --clean --if-exists npi-2026-10-21-1200.dump
```

Verify before switching traffic:

```bash
psql -h db-host -U npi -d npi_restored -c "select count(*) from simulation_runs;"
psql -h db-host -U npi -d npi_restored -c "select count(*) from audit_logs;"
```

### Docker Compose

```bash
docker compose exec -T db pg_dump -U npi -Fc npi > npi-$(date +%F-%H%M).dump
docker compose cp npi-$(date +%F-%H%M).dump db:/tmp/restore.dump
docker compose exec -T db pg_restore -U npi -d npi --clean --if-exists /tmp/restore.dump
```

---

## SQLite (development and single-user deployments)

```bash
# Safe online copy (WAL aware)
sqlite3 backend/npi.db ".backup 'npi-$(date +%F-%H%M).sqlite3'"

# Or copy the three files together while the service is stopped
cp backend/npi.db backend/npi.db-wal backend/npi.db-shm /backup/ 2>/dev/null
```

Restore by replacing the file and restarting the API:

```bash
cp /backup/npi-2026-10-21-1200.sqlite3 backend/npi.db
rm -f backend/npi.db-wal backend/npi.db-shm
```

---

## What to back up

| Data | Where | Why |
|---|---|---|
| Simulation runs and samples | `simulation_runs` | The forecast of record, including seed and configuration |
| Forecast snapshots | `simulation_snapshots` | What the forecast was when a decision was taken |
| Optimisation runs | `optimization_runs` | The verified recommendation and its economics |
| Scenarios and interventions | `scenarios`, `interventions` | What was compared and approved |
| Audit log | `audit_logs` | Who did what, when, with which parameters |
| AI conversations | `ai_conversations`, `ai_messages` | Decision rationale (provider keys are *not* stored here) |
| Provider configuration | `ai_provider_configs` | Encrypted; re-encrypt if `SECRET_KEY` changes |
| Program definitions | `projects` … `milestones` | The digital twin itself |

---

## Retention and verification

* **Verify a restore quarterly.** A backup that has never been restored is a
  hypothesis, not a backup.
* **Keep run records long term.** They are small (a few MB per 2,000-trial run) and
  they are what makes a decision defensible months later.
* **Do not back up `.env` in the clear.** If provider keys must survive a restore,
  store the `SECRET_KEY` in your secret manager and re-enter the keys in the UI.
* **Rotate the secret key** with a planned re-encryption: stored provider
  configurations are encrypted with a key derived from it.
