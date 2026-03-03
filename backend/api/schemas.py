"""
backend/api/schemas.py
──────────────────────
Pydantic v2 response models.  These define exactly what JSON shape each
endpoint returns and auto-generate the OpenAPI docs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Shared base ───────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectOut(OrmBase):
    id:              int
    jira_key:        str
    name:            str
    description:     str | None = None
    lead_email:      str | None = None
    board_id:        int | None = None
    synced_at:       str | None = None


# ── Sprints ───────────────────────────────────────────────────────────────────

class SprintOut(OrmBase):
    id:              int
    jira_sprint_id:  int
    name:            str
    state:           str
    goal:            str | None = None
    start_date:      str | None = None
    end_date:        str | None = None
    complete_date:   str | None = None


# ── Velocity ──────────────────────────────────────────────────────────────────

class VelocitySprintRow(BaseModel):
    sprint_id:        int
    sprint_name:      str
    complete_date:    str | None
    start_date:       str | None
    end_date:         str | None
    completed_points: float | None
    committed_points: float | None
    total_issues:     int
    done_issues:      int


class VelocityResponse(BaseModel):
    average_completed_points: float | None
    average_committed_points: float | None
    predictability_pct:       float | None
    sprints_analysed:         int
    window:                   int
    trend:                    list[VelocitySprintRow]


# ── Scope Creep ───────────────────────────────────────────────────────────────

class AddedIssue(BaseModel):
    jira_issue_id:   str
    summary:         str
    issue_type:      str | None
    priority:        str | None
    status:          str | None
    story_points:    float | None
    assignee_email:  str | None
    created_at_jira: str | None


class ScopeCreepSprintRow(BaseModel):
    sprint_id:          int
    sprint_name:        str
    state:              str
    start_date:         str | None
    end_date:           str | None
    original_issues:    int
    added_issues:       int
    total_issues:       int
    original_points:    float | None
    added_points:       float | None
    total_points:       float | None
    scope_creep_pct:    float | None
    added_issue_detail: list[AddedIssue]


# ── Cycle Time ────────────────────────────────────────────────────────────────

class CycleTimeIssueRow(BaseModel):
    id:             int
    jira_issue_id:  str
    summary:        str
    issue_type:     str | None
    story_points:   float | None
    assignee_email: str | None
    in_progress_at: str | None
    done_at:        str | None
    cycle_days:     float | None


class CycleTimeResponse(BaseModel):
    mean_days:   float | None
    p50_days:    float | None
    p75_days:    float | None
    p95_days:    float | None
    stddev_days: float | None
    sample_size: int
    issue_type:  str | None
    sprint_id:   int | None


# ── Sprint Completion ─────────────────────────────────────────────────────────

class SprintCompletionRow(BaseModel):
    sprint_id:               int
    sprint_name:             str
    state:                   str
    start_date:              str | None
    end_date:                str | None
    complete_date:           str | None
    total_issues:            int
    done_issues:             int
    completion_pct_issues:   float | None
    total_points:            float | None
    done_points:             float | None
    in_progress_points:      float | None
    todo_points:             float | None
    completion_pct_points:   float | None


# ── Backlog Readiness ─────────────────────────────────────────────────────────

class BacklogByTypeRow(BaseModel):
    issue_type: str | None
    count:      int


class BacklogReadinessResponse(BaseModel):
    total_backlog:          int
    with_ac:                int
    with_points:            int
    fully_ready:            int
    ac_readiness_pct:       float | None
    points_readiness_pct:   float | None
    full_readiness_pct:     float | None
    by_issue_type:          list[BacklogByTypeRow]


# ── Story Point Distribution ──────────────────────────────────────────────────

class StatusCategoryRow(BaseModel):
    status_category: str | None
    issue_count:     int
    total_points:    float | None
    pct_of_total:    float | None


class IssueTypeRow(BaseModel):
    issue_type:      str | None
    status_category: str | None
    issue_count:     int
    total_points:    float | None


class DistributionResponse(BaseModel):
    by_status: list[StatusCategoryRow]
    by_type:   list[IssueTypeRow]
    sprint_id: int | None


# ── Delivery Health ───────────────────────────────────────────────────────────

class HealthVelocitySnippet(BaseModel):
    average_completed_points: float | None
    predictability_pct:       float | None
    sprints_analysed:         int


class HealthCycleTimeSnippet(BaseModel):
    mean_days:   float | None
    p50_days:    float | None
    p95_days:    float | None
    sample_size: int


class HealthBacklogSnippet(BaseModel):
    total:              int
    full_readiness_pct: float | None
    ac_readiness_pct:   float | None


class HealthCurrentSprint(BaseModel):
    sprint_name:            str
    completion_pct_points:  float | None
    scope_creep_pct:        float | None


class DeliveryHealthResponse(BaseModel):
    velocity:        HealthVelocitySnippet
    cycle_time:      HealthCycleTimeSnippet
    backlog:         HealthBacklogSnippet
    current_sprint:  HealthCurrentSprint | None


# ── Generic error ─────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str


# ── Time Tracking ─────────────────────────────────────────────────────────────
class TimeTrackingRow(BaseModel):
    sprint_name: str
    estimated_hours: float | None
    spent_hours: float | None