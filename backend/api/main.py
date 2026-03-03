"""
backend/api/main.py
────────────────────
FastAPI application factory.

Start the server
────────────────
    uvicorn backend.api.main:app --reload --port 8000

Interactive docs
────────────────
    http://localhost:8000/docs       (Swagger UI)
    http://localhost:8000/redoc      (ReDoc)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.api import analytics as analytics_router
from backend.api import projects as projects_router
from backend.core.config import settings
from backend.db.session import SessionLocal, engine

# ── App instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Jira Delivery Analytics API",
    description=(
        "REST API for the Product Requirements & Delivery Analytics Platform. "
        "Surfaces velocity, scope creep, cycle time, and backlog health metrics "
        "derived from synced Jira data."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the React / Streamlit frontend to call the API from a different port.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(projects_router.router)
app.include_router(analytics_router.router)


# ── Root & health ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {"message": "Jira Analytics API — see /docs for endpoints"}


@app.get("/healthz", tags=["system"], summary="Health check")
def health_check():
    """
    Lightweight liveness probe.
    Returns 200 if the API process is running and the DB is reachable.
    Returns 503 if the DB connection fails.
    """
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status":    "degraded",
                "db":        "unreachable",
                "error":     str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {
        "status":    "ok",
        "db":        db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/meta", tags=["system"], summary="API metadata")
def api_meta():
    """Return basic metadata: available projects and last sync times."""
    with SessionLocal() as db:
        rows = db.execute(
            text("""
                SELECT p.jira_key, p.name, p.synced_at::text,
                       (SELECT MAX(started_at)::text FROM sync_log sl
                        WHERE sl.project_id = p.id AND sl.status = 'success') AS last_sync_ok
                FROM projects p
                ORDER BY p.name
            """)
        ).fetchall()

    return {
        "projects": [dict(r._mapping) for r in rows],
        "velocity_default_window": settings.velocity_window,
    }
