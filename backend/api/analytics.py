"""
backend/api/analytics.py
─────────────────────────
All metric endpoints.  Every route is scoped to a project key so the
frontend can switch between projects without re-wiring any calls.

Routes
──────
GET /api/{project_key}/metrics/velocity
GET /api/{project_key}/metrics/scope-creep
GET /api/{project_key}/metrics/cycle-time
GET /api/{project_key}/metrics/cycle-time/distribution
GET /api/{project_key}/metrics/sprint-completion
GET /api/{project_key}/metrics/backlog-readiness
GET /api/{project_key}/metrics/distribution
GET /api/{project_key}/metrics/health
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.schemas import (
    BacklogReadinessResponse,
    CycleTimeIssueRow,
    CycleTimeResponse,
    DeliveryHealthResponse,
    DistributionResponse,
    ErrorResponse,
    ScopeCreepSprintRow,
    SprintCompletionRow,
    VelocityResponse,
    TimeTrackingRow,
)
from backend.db.session import get_db
from backend.services import analytics as svc

router = APIRouter(tags=["analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# Shared dependency: resolve project_key → project_id
# ─────────────────────────────────────────────────────────────────────────────

def _get_project_id(project_key: str, db: Session) -> int:
    row = db.execute(
        text("SELECT id FROM projects WHERE jira_key = :key"),
        {"key": project_key.upper()},
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_key}' not found. Run the sync first.",
        )
    return row.id


# ─────────────────────────────────────────────────────────────────────────────
# Velocity
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/velocity",
    response_model=VelocityResponse,
    summary="Sprint velocity",
    description=(
        "Average story points completed per sprint over the last `window` "
        "closed sprints, plus a per-sprint breakdown for charting."
    ),
)
def get_velocity(
    project_key: str,
    window: int = Query(default=3, ge=1, le=20, description="Number of closed sprints to average"),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.velocity(db, project_id, window=window)


# ─────────────────────────────────────────────────────────────────────────────
# Scope Creep
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/scope-creep",
    response_model=list[ScopeCreepSprintRow],
    summary="Scope creep per sprint",
    description=(
        "Issues and story points added to a sprint after it started. "
        "Includes a per-issue breakdown of exactly what was added."
    ),
)
def get_scope_creep(
    project_key: str,
    limit: int = Query(default=5, ge=1, le=20, description="Max number of sprints to return"),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.scope_creep(db, project_id, limit=limit)


# ─────────────────────────────────────────────────────────────────────────────
# Cycle Time
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/cycle-time",
    response_model=CycleTimeResponse,
    summary="Cycle time statistics",
    description=(
        "Average, median (p50), p75, p95, and stddev of the time (in days) "
        "an issue spends from 'In Progress' to 'Done'. "
        "Filter by issue_type (e.g. Story) or a specific sprint_id."
    ),
)
def get_cycle_time(
    project_key: str,
    issue_type: str | None = Query(default=None, description="e.g. Story, Bug, Task"),
    sprint_id: int | None = Query(default=None, description="Scope to a single sprint"),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.cycle_time(db, project_id, issue_type=issue_type, sprint_id=sprint_id)


@router.get(
    "/api/{project_key}/metrics/cycle-time/distribution",
    response_model=list[CycleTimeIssueRow],
    summary="Per-issue cycle time (scatter / histogram data)",
    description=(
        "Returns individual cycle-time observations. Use this to power "
        "scatter plots or histograms in the frontend."
    ),
)
def get_cycle_time_distribution(
    project_key: str,
    issue_type: str | None = Query(default=None),
    sprint_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.cycle_time_distribution(db, project_id, issue_type=issue_type, sprint_id=sprint_id)


# ─────────────────────────────────────────────────────────────────────────────
# Sprint Completion
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/sprint-completion",
    response_model=list[SprintCompletionRow],
    summary="Sprint completion percentage",
    description=(
        "Percentage of committed story points and issues completed per sprint. "
        "Also returns in-progress and to-do point breakdowns for stacked bars."
    ),
)
def get_sprint_completion(
    project_key: str,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.sprint_completion(db, project_id, limit=limit)


# ─────────────────────────────────────────────────────────────────────────────
# Backlog Readiness
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/backlog-readiness",
    response_model=BacklogReadinessResponse,
    summary="Backlog readiness",
    description=(
        "Percentage of open backlog items (not yet in a sprint) that have "
        "acceptance criteria, story point estimates, or both. "
        "Broken down by issue type."
    ),
)
def get_backlog_readiness(
    project_key: str,
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.backlog_readiness(db, project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Story Point Distribution
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/distribution",
    response_model=DistributionResponse,
    summary="Story point distribution by status",
    description=(
        "Distribution of story points and issue counts across status categories "
        "(To Do / In Progress / Done). Optionally scoped to a sprint. "
        "Use for pie charts and stacked bar charts on the Delivery Health dashboard."
    ),
)
def get_distribution(
    project_key: str,
    sprint_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.story_point_distribution(db, project_id, sprint_id=sprint_id)


# ─────────────────────────────────────────────────────────────────────────────
# Delivery Health (summary card)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/health",
    response_model=DeliveryHealthResponse,
    summary="Delivery health summary",
    description=(
        "Aggregates velocity, cycle time, backlog readiness, and current sprint "
        "progress into a single response. Ideal for a dashboard header / KPI card."
    ),
)
def get_delivery_health(
    project_key: str,
    velocity_window: int = Query(default=3, ge=1, le=20),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.delivery_health(db, project_id, velocity_window=velocity_window)

# ─────────────────────────────────────────────────────────────────────────────
# Time Tracking
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/api/{project_key}/metrics/time-tracking",
    response_model=list[TimeTrackingRow],
    summary="Estimated vs Spent Hours"
)
def get_time_tracking(
    project_key: str,
    limit: int = Query(default=5),
    db: Session = Depends(get_db),
):
    project_id = _get_project_id(project_key, db)
    return svc.time_tracking(db, project_id, limit=limit)