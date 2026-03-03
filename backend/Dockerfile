# ─────────────────────────────────────────────────────────────────────────────
# backend/Dockerfile
# Build context: project root  (set in docker-compose.yml)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
# postgresql-client  → provides psql (schema apply) and pg_isready (health check)
# curl               → useful for container debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
# Copy the full project root so scripts/ and db/ are available alongside backend/
COPY . .

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
