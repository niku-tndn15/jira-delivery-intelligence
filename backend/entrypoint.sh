#!/usr/bin/env bash
# =============================================================================
# backend/entrypoint.sh
#
# Startup sequence every time the backend container boots:
#   1. Wait for PostgreSQL to accept connections
#   2. Apply db/schema.sql (idempotent — skipped if tables already exist)
#   3. Run the initial Jira sync for $JIRA_PROJECT_KEY
#   4. Start the uvicorn server
# =============================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[entrypoint]${NC} $*"; }
warn() { echo -e "${YELLOW}[entrypoint]${NC} $*"; }
err()  { echo -e "${RED}[entrypoint]${NC} $*" >&2; }

# ── 1. Validate required environment variables ─────────────────────────────────
REQUIRED_VARS=(DATABASE_URL JIRA_BASE_URL JIRA_EMAIL JIRA_API_TOKEN JIRA_PROJECT_KEY)
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    err "Required environment variable '$var' is not set."
    err "Add it to your .env file and re-run 'docker-compose up'."
    exit 1
  fi
done

log "Starting Jira Analytics backend for project: ${JIRA_PROJECT_KEY}"

# ── 2. Wait for PostgreSQL ─────────────────────────────────────────────────────
# pg_isready ships with postgresql-client (installed in the Dockerfile).
# It exits 0 only when the server is accepting connections.

# Parse host and port from DATABASE_URL
# Expected format: postgresql://user:pass@host:port/dbname
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:/]+).*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
DB_PORT=${DB_PORT:-5432}

log "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."

MAX_RETRIES=30
RETRY=0
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U postgres -q; do
  RETRY=$((RETRY + 1))
  if [[ $RETRY -ge $MAX_RETRIES ]]; then
    err "PostgreSQL did not become ready after ${MAX_RETRIES} attempts. Aborting."
    exit 1
  fi
  warn "  Postgres not ready yet (attempt ${RETRY}/${MAX_RETRIES}) — retrying in 2s..."
  sleep 2
done

log "PostgreSQL is ready."

# ── 3. Apply database schema (idempotent) ─────────────────────────────────────
# Check whether the 'projects' table already exists.
# If it does, the schema has already been applied — skip to avoid duplicate-index errors.
TABLE_EXISTS=$(psql "$DATABASE_URL" -tAc \
  "SELECT EXISTS (
     SELECT 1 FROM information_schema.tables
     WHERE table_schema = 'public' AND table_name = 'projects'
   );" 2>/dev/null || echo "f")

if [[ "$TABLE_EXISTS" == "t" ]]; then
  log "Schema already applied — skipping."
else
  log "Applying database schema from db/schema.sql ..."
  psql "$DATABASE_URL" -f db/schema.sql
  log "Schema applied successfully."
fi

# ── 4. Run initial Jira sync ───────────────────────────────────────────────────
# Uses the same CLI that works locally:
#   python scripts/jira_sync.py --project GETSCTCL
#
# On subsequent container restarts this performs an incremental sync
# (only fetches issues updated since the last run).

log "Running Jira sync for project '${JIRA_PROJECT_KEY}' ..."
if python scripts/jira_sync.py --project "${JIRA_PROJECT_KEY}"; then
  log "Jira sync completed successfully."
else
  # A failed sync is non-fatal: the API can still serve any data already
  # in the database from a previous run. Log the warning and continue.
  warn "Jira sync failed or returned a non-zero exit code."
  warn "The server will start anyway. Check the logs above for details."
  warn "You can trigger a manual re-sync with:"
  warn "  docker-compose exec backend python scripts/jira_sync.py --project ${JIRA_PROJECT_KEY}"
fi

# ── 5. Start the FastAPI server ────────────────────────────────────────────────
log "Starting uvicorn on 0.0.0.0:8000 ..."
exec uvicorn backend.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 2 \
  --log-level info
