"""
backend/services/analytics.py
──────────────────────────────
Pure analytics functions.  Every function accepts a live SQLAlchemy Session
and returns plain Python dicts/lists so the API layer can serialise them
with Pydantic without extra conversion.

Metrics implemented
───────────────────
  velocity()              – avg story points completed per sprint (last N sprints)
  velocity_trend()        – per-sprint breakdown for a sparkline / bar chart
  scope_creep()           – issues + points added to a sprint after it started
  cycle_time()            – avg/p50/p75/p95 days from In Progress → Done
  cycle_time_distribution()  – per-issue breakdown for scatter / histogram
  sprint_completion()     – % of committed points completed per sprint
  backlog_readiness()     – % of open backlog stories with acceptance criteria
  delivery_health()       – aggregated summary card for the dashboard header
  story_point_distribution() – count/points grouped by status category
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

"""
def _df(session: Session, sql: str, params: dict | None = None) -> pd.DataFrame:
    #Execute raw SQL and return a DataFrame. Handles empty result sets.
    result = session.execute(text(sql), params or {})
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=result.keys())
    return pd.DataFrame(rows, columns=result.keys())
"""

def _df(session: Session, sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute raw SQL and return a DataFrame. Handles empty result sets."""
    result = session.execute(text(sql), params or {})
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=result.keys())
    
    # 1. Create the DataFrame as usual
    df = pd.DataFrame(rows, columns=result.keys())
    
    # 2. ── THE FIX ──────────────────────────────────────────────────────────
    # Convert Pandas NaN / NaT values into strict Python None types 
    # so Pydantic doesn't throw a ResponseValidationError for missing emails.
    df = df.astype(object).where(pd.notnull(df), None)
    
    return df


def _round(value: float | None, decimals: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), decimals)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Velocity
# ─────────────────────────────────────────────────────────────────────────────

_VELOCITY_SQL = """
WITH closed_sprints AS (
    SELECT
        s.id,
        s.name,
        s.complete_date,
        s.start_date,
        s.end_date,
        -- Sum story points of Done issues in this sprint
        COALESCE(SUM(
            CASE WHEN i.status_category = 'Done' THEN i.story_points ELSE 0 END
        ), 0)                                   AS completed_points,
        -- Sum ALL story points committed at sprint start (not added mid-sprint)
        COALESCE(SUM(
            CASE WHEN NOT i.added_mid_sprint THEN i.story_points ELSE 0 END
        ), 0)                                   AS committed_points,
        COUNT(i.id)                             AS total_issues,
        COUNT(CASE WHEN i.status_category = 'Done' THEN 1 END) AS done_issues
    FROM sprints s
    LEFT JOIN issues i ON i.sprint_id = s.id
    WHERE s.project_id  = :project_id
      AND s.state        = 'closed'
    GROUP BY s.id, s.name, s.complete_date, s.start_date, s.end_date
    ORDER BY s.complete_date DESC
    LIMIT :window
)
SELECT * FROM closed_sprints ORDER BY complete_date ASC
"""


def velocity_trend(
    session: Session,
    project_id: int,
    window: int = 3,
) -> list[dict[str, Any]]:
    """
    Return per-sprint completed/committed points for the last `window`
    closed sprints, oldest first (good for charting).
    """
    df = _df(session, _VELOCITY_SQL, {"project_id": project_id, "window": window})
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "sprint_id":        int(row["id"]),
                "sprint_name":      row["name"],
                "complete_date":    row["complete_date"].isoformat() if row["complete_date"] else None,
                "start_date":       row["start_date"].isoformat() if row["start_date"] else None,
                "end_date":         row["end_date"].isoformat() if row["end_date"] else None,
                "completed_points": _round(row["completed_points"]),
                "committed_points": _round(row["committed_points"]),
                "total_issues":     int(row["total_issues"]),
                "done_issues":      int(row["done_issues"]),
            }
        )
    return records


def velocity(
    session: Session,
    project_id: int,
    window: int = 3,
) -> dict[str, Any]:
    """
    Average velocity (completed story points) over the last `window` closed sprints.
    Also returns the trend so callers don't need a second call.
    """
    trend = velocity_trend(session, project_id, window)
    if not trend:
        return {
            "average_completed_points": None,
            "average_committed_points": None,
            "predictability_pct":       None,
            "sprints_analysed":         0,
            "window":                   window,
            "trend":                    [],
        }

    avg_completed = sum(s["completed_points"] for s in trend) / len(trend)
    avg_committed = sum(s["committed_points"] for s in trend) / len(trend)
    predictability = (avg_completed / avg_committed * 100) if avg_committed else None

    return {
        "average_completed_points": _round(avg_completed),
        "average_committed_points": _round(avg_committed),
        "predictability_pct":       _round(predictability),
        "sprints_analysed":         len(trend),
        "window":                   window,
        "trend":                    trend,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scope Creep
# ─────────────────────────────────────────────────────────────────────────────

_SCOPE_CREEP_SQL = """
SELECT
    s.id                                        AS sprint_id,
    s.name                                      AS sprint_name,
    s.state,
    s.start_date,
    s.end_date,
    -- Issues added mid-sprint
    COUNT(CASE WHEN i.added_mid_sprint THEN 1 END)   AS added_issues,
    COUNT(CASE WHEN NOT i.added_mid_sprint THEN 1 END) AS original_issues,
    COUNT(i.id)                                 AS total_issues,
    -- Story points added mid-sprint
    COALESCE(SUM(
        CASE WHEN i.added_mid_sprint THEN i.story_points ELSE 0 END
    ), 0)                                       AS added_points,
    COALESCE(SUM(
        CASE WHEN NOT i.added_mid_sprint THEN i.story_points ELSE 0 END
    ), 0)                                       AS original_points,
    COALESCE(SUM(i.story_points), 0)            AS total_points
FROM sprints s
LEFT JOIN issues i ON i.sprint_id = s.id
WHERE s.project_id = :project_id
  AND s.state IN ('active', 'closed')
GROUP BY s.id, s.name, s.state, s.start_date, s.end_date
ORDER BY s.start_date DESC
LIMIT :limit
"""

_SCOPE_CREEP_ISSUES_SQL = """
SELECT
    i.jira_issue_id,
    i.summary,
    i.issue_type,
    i.priority,
    i.status,
    i.story_points,
    i.assignee_email,
    i.created_at_jira
FROM issues i
WHERE i.sprint_id      = :sprint_id
  AND i.added_mid_sprint = TRUE
ORDER BY i.created_at_jira ASC
"""


def scope_creep(
    session: Session,
    project_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Scope creep per sprint: issues/points added after the sprint started.
    Returns the last `limit` active or closed sprints.
    """
    df = _df(session, _SCOPE_CREEP_SQL, {"project_id": project_id, "limit": limit})
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        total   = float(row["total_points"])  or 0
        added   = float(row["added_points"])  or 0
        creep_pct = _round((added / total * 100) if total else 0)

        # Fetch the individual issues added mid-sprint for this sprint
        issues_df = _df(
            session, _SCOPE_CREEP_ISSUES_SQL, {"sprint_id": int(row["sprint_id"])}
        )
        added_issues_list = [
            {
                "jira_issue_id": r["jira_issue_id"],
                "summary":       r["summary"],
                "issue_type":    r["issue_type"],
                "priority":      r["priority"],
                "status":        r["status"],
                "story_points":  _round(r["story_points"]),
                "assignee_email":r["assignee_email"],
                "created_at_jira": r["created_at_jira"].isoformat() if r["created_at_jira"] else None,
            }
            for _, r in issues_df.iterrows()
        ]

        records.append(
            {
                "sprint_id":       int(row["sprint_id"]),
                "sprint_name":     row["sprint_name"],
                "state":           row["state"],
                "start_date":      row["start_date"].isoformat() if row["start_date"] else None,
                "end_date":        row["end_date"].isoformat() if row["end_date"] else None,
                "original_issues": int(row["original_issues"]),
                "added_issues":    int(row["added_issues"]),
                "total_issues":    int(row["total_issues"]),
                "original_points": _round(row["original_points"]),
                "added_points":    _round(row["added_points"]),
                "total_points":    _round(row["total_points"]),
                "scope_creep_pct": creep_pct,
                "added_issue_detail": added_issues_list,
            }
        )
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cycle Time
# ─────────────────────────────────────────────────────────────────────────────

_CYCLE_TIME_SQL = """
SELECT
    i.id,
    i.jira_issue_id,
    i.summary,
    i.issue_type,
    i.story_points,
    i.assignee_email,
    i.in_progress_at,
    i.done_at,
    -- Cycle time in fractional days
    EXTRACT(EPOCH FROM (i.done_at - i.in_progress_at)) / 86400.0  AS cycle_days
FROM issues i
WHERE i.project_id    = :project_id
  AND i.in_progress_at IS NOT NULL
  AND i.done_at        IS NOT NULL
  AND i.done_at > i.in_progress_at
  AND (:issue_type IS NULL OR i.issue_type = :issue_type)
  AND (:sprint_id  IS NULL OR i.sprint_id  = :sprint_id)
ORDER BY i.done_at DESC
"""


def cycle_time_distribution(
    session: Session,
    project_id: int,
    issue_type: str | None = None,
    sprint_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Per-issue cycle time (days). Useful for scatter plots and histograms.
    Optionally filter by issue_type (e.g. 'Story') or a specific sprint.
    """
    df = _df(
        session,
        _CYCLE_TIME_SQL,
        {"project_id": project_id, "issue_type": issue_type, "sprint_id": sprint_id},
    )
    if df.empty:
        return []

    return [
        {
            "id":             int(row["id"]),
            "jira_issue_id":  row["jira_issue_id"],
            "summary":        row["summary"],
            "issue_type":     row["issue_type"],
            "story_points":   _round(row["story_points"]),
            "assignee_email": row["assignee_email"],
            "in_progress_at": row["in_progress_at"].isoformat() if row["in_progress_at"] else None,
            "done_at":        row["done_at"].isoformat() if row["done_at"] else None,
            "cycle_days":     _round(row["cycle_days"]),
        }
        for _, row in df.iterrows()
    ]


def cycle_time(
    session: Session,
    project_id: int,
    issue_type: str | None = None,
    sprint_id: int | None = None,
) -> dict[str, Any]:
    """
    Aggregate cycle-time stats: mean, median (p50), p75, p95, and stddev.
    """
    distribution = cycle_time_distribution(session, project_id, issue_type, sprint_id)
    if not distribution:
        return {
            "mean_days":   None,
            "p50_days":    None,
            "p75_days":    None,
            "p95_days":    None,
            "stddev_days": None,
            "sample_size": 0,
            "issue_type":  issue_type,
            "sprint_id":   sprint_id,
        }

    series = pd.Series([d["cycle_days"] for d in distribution], dtype=float)
    return {
        "mean_days":   _round(series.mean()),
        "p50_days":    _round(series.quantile(0.50)),
        "p75_days":    _round(series.quantile(0.75)),
        "p95_days":    _round(series.quantile(0.95)),
        "stddev_days": _round(series.std()),
        "sample_size": len(series),
        "issue_type":  issue_type,
        "sprint_id":   sprint_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Sprint Completion Percentage
# ─────────────────────────────────────────────────────────────────────────────

_SPRINT_COMPLETION_SQL = """
SELECT
    s.id                                            AS sprint_id,
    s.name                                          AS sprint_name,
    s.state,
    s.start_date,
    s.end_date,
    s.complete_date,
    COUNT(i.id)                                     AS total_issues,
    COUNT(CASE WHEN i.status_category = 'Done' THEN 1 END) AS done_issues,
    COALESCE(SUM(i.story_points), 0)                AS total_points,
    COALESCE(SUM(
        CASE WHEN i.status_category = 'Done' THEN i.story_points ELSE 0 END
    ), 0)                                           AS done_points,
    COALESCE(SUM(
        CASE WHEN i.status_category = 'In Progress' THEN i.story_points ELSE 0 END
    ), 0)                                           AS in_progress_points,
    COALESCE(SUM(
        CASE WHEN i.status_category = 'To Do' THEN i.story_points ELSE 0 END
    ), 0)                                           AS todo_points
FROM sprints s
LEFT JOIN issues i ON i.sprint_id = s.id
WHERE s.project_id = :project_id
  AND s.state IN ('active', 'closed')
GROUP BY s.id, s.name, s.state, s.start_date, s.end_date, s.complete_date
ORDER BY s.start_date DESC
LIMIT :limit
"""


def sprint_completion(
    session: Session,
    project_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Sprint completion percentage (by issues and by story points)
    for the last `limit` active or closed sprints.
    """
    df = _df(session, _SPRINT_COMPLETION_SQL, {"project_id": project_id, "limit": limit})
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        total_pts = float(row["total_points"]) or 0
        done_pts  = float(row["done_points"])  or 0
        total_iss = int(row["total_issues"])   or 0
        done_iss  = int(row["done_issues"])    or 0

        records.append(
            {
                "sprint_id":            int(row["sprint_id"]),
                "sprint_name":          row["sprint_name"],
                "state":                row["state"],
                "start_date":           row["start_date"].isoformat() if row["start_date"] else None,
                "end_date":             row["end_date"].isoformat() if row["end_date"] else None,
                "complete_date":        row["complete_date"].isoformat() if row["complete_date"] else None,
                "total_issues":         total_iss,
                "done_issues":          done_iss,
                "completion_pct_issues":_round((done_iss  / total_iss  * 100) if total_iss  else 0),
                "total_points":         _round(total_pts),
                "done_points":          _round(done_pts),
                "in_progress_points":   _round(row["in_progress_points"]),
                "todo_points":          _round(row["todo_points"]),
                "completion_pct_points":_round((done_pts  / total_pts  * 100) if total_pts  else 0),
            }
        )
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 5. Backlog Readiness
# ─────────────────────────────────────────────────────────────────────────────

_BACKLOG_READINESS_SQL = """
SELECT
    COUNT(*)                                          AS total_backlog,
    COUNT(CASE WHEN has_ac THEN 1 END)                AS with_ac,
    COUNT(CASE WHEN story_points IS NOT NULL THEN 1 END) AS with_points,
    COUNT(CASE WHEN has_ac AND story_points IS NOT NULL THEN 1 END) AS fully_ready,
    -- Break down by issue type
    issue_type,
    COUNT(*) FILTER (WHERE true)                      AS type_count
FROM issues
WHERE project_id     = :project_id
  AND status_category != 'Done'
  AND sprint_id IS NULL      -- backlog only (not in a sprint)
  AND issue_type IN ('Story', 'Bug', 'Task')
GROUP BY issue_type
"""

_BACKLOG_TOTAL_SQL = """
SELECT
    COUNT(*)                                              AS total_backlog,
    COUNT(CASE WHEN has_ac THEN 1 END)                    AS with_ac,
    COUNT(CASE WHEN story_points IS NOT NULL THEN 1 END)  AS with_points,
    COUNT(CASE WHEN has_ac AND story_points IS NOT NULL THEN 1 END) AS fully_ready
FROM issues
WHERE project_id      = :project_id
  AND status_category != 'Done'
  AND sprint_id IS NULL
  AND issue_type IN ('Story', 'Bug', 'Task')
"""


def backlog_readiness(
    session: Session,
    project_id: int,
) -> dict[str, Any]:
    """
    Percentage of open backlog stories that have:
      - Acceptance criteria (has_ac)
      - Story points estimated
      - Both (fully ready)
    """
    total_df = _df(session, _BACKLOG_TOTAL_SQL, {"project_id": project_id})
    by_type_df = _df(session, _BACKLOG_READINESS_SQL, {"project_id": project_id})

    if total_df.empty or int(total_df.iloc[0]["total_backlog"]) == 0:
        return {
            "total_backlog":      0,
            "with_ac":            0,
            "with_points":        0,
            "fully_ready":        0,
            "ac_readiness_pct":   None,
            "points_readiness_pct": None,
            "full_readiness_pct": None,
            "by_issue_type":      [],
        }

    row   = total_df.iloc[0]
    total = int(row["total_backlog"])
    w_ac  = int(row["with_ac"])
    w_pts = int(row["with_points"])
    ready = int(row["fully_ready"])

    by_type = []
    if not by_type_df.empty:
        for _, tr in by_type_df.iterrows():
            by_type.append(
                {
                    "issue_type": tr["issue_type"],
                    "count":      int(tr["type_count"]),
                }
            )

    return {
        "total_backlog":        total,
        "with_ac":              w_ac,
        "with_points":          w_pts,
        "fully_ready":          ready,
        "ac_readiness_pct":     _round(w_ac  / total * 100),
        "points_readiness_pct": _round(w_pts / total * 100),
        "full_readiness_pct":   _round(ready / total * 100),
        "by_issue_type":        by_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Story Point Distribution (for Delivery Health pie / stacked bar)
# ─────────────────────────────────────────────────────────────────────────────

_DISTRIBUTION_SQL = """
SELECT
    status_category,
    issue_type,
    COUNT(*)                        AS issue_count,
    COALESCE(SUM(story_points), 0)  AS total_points
FROM issues
WHERE project_id = :project_id
  AND (:sprint_id IS NULL OR sprint_id = :sprint_id)
GROUP BY status_category, issue_type
ORDER BY status_category, issue_type
"""


def story_point_distribution(
    session: Session,
    project_id: int,
    sprint_id: int | None = None,
) -> dict[str, Any]:
    """
    Distribution of story points (and issue counts) across status categories.
    Optionally scoped to a single sprint.
    """
    df = _df(session, _DISTRIBUTION_SQL, {"project_id": project_id, "sprint_id": sprint_id})
    if df.empty:
        return {"by_status": [], "by_type": [], "sprint_id": sprint_id}

    # Group by status_category
    by_status = (
        df.groupby("status_category")
        .agg(issue_count=("issue_count", "sum"), total_points=("total_points", "sum"))
        .reset_index()
    )
    grand_total_pts = float(by_status["total_points"].sum()) or 0

    status_rows = [
        {
            "status_category": row["status_category"],
            "issue_count":     int(row["issue_count"]),
            "total_points":    _round(row["total_points"]),
            "pct_of_total":    _round(
                float(row["total_points"]) / grand_total_pts * 100
                if grand_total_pts else 0
            ),
        }
        for _, row in by_status.iterrows()
    ]

    # Flat rows per issue_type
    type_rows = [
        {
            "issue_type":      row["issue_type"],
            "status_category": row["status_category"],
            "issue_count":     int(row["issue_count"]),
            "total_points":    _round(row["total_points"]),
        }
        for _, row in df.iterrows()
    ]

    return {
        "by_status":  status_rows,
        "by_type":    type_rows,
        "sprint_id":  sprint_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Delivery Health Summary  (single card for dashboard header)
# ─────────────────────────────────────────────────────────────────────────────

def delivery_health(
    session: Session,
    project_id: int,
    velocity_window: int = 3,
) -> dict[str, Any]:
    """
    Combines all key metrics into one response — ideal for a summary card
    or a /health dashboard endpoint that powers a single page load.
    """
    vel   = velocity(session, project_id, velocity_window)
    ct    = cycle_time(session, project_id, issue_type="Story")
    br    = backlog_readiness(session, project_id)
    sc    = scope_creep(session, project_id, limit=1)
    comp  = sprint_completion(session, project_id, limit=1)

    # Current / last sprint summary
    current_sprint   = comp[0]  if comp  else None
    last_scope_creep = sc[0]    if sc    else None

    return {
        "velocity": {
            "average_completed_points": vel["average_completed_points"],
            "predictability_pct":       vel["predictability_pct"],
            "sprints_analysed":         vel["sprints_analysed"],
        },
        "cycle_time": {
            "mean_days":  ct["mean_days"],
            "p50_days":   ct["p50_days"],
            "p95_days":   ct["p95_days"],
            "sample_size":ct["sample_size"],
        },
        "backlog": {
            "total":              br["total_backlog"],
            "full_readiness_pct": br["full_readiness_pct"],
            "ac_readiness_pct":   br["ac_readiness_pct"],
        },
        "current_sprint": (
            {
                "sprint_name":          current_sprint["sprint_name"],
                "completion_pct_points":current_sprint["completion_pct_points"],
                "scope_creep_pct":      last_scope_creep["scope_creep_pct"] if last_scope_creep else None,
            }
            if current_sprint else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Time Tracking
# ─────────────────────────────────────────────────────────────────────────────

def time_tracking(session: Session, project_id: int, limit: int = 5) -> list[dict]:
    """Calculate Estimated vs Spent hours per sprint."""
    sql = """
        SELECT
            s.name as sprint_name,
            ROUND(SUM(i.original_estimate) / 3600.0, 1) as estimated_hours,
            ROUND(SUM(i.time_spent) / 3600.0, 1) as spent_hours
        FROM sprints s
        JOIN issues i ON i.sprint_id = s.id
        WHERE s.project_id = :pid AND s.state != 'future'
        GROUP BY s.id, s.name, s.start_date
        ORDER BY s.start_date DESC NULLS LAST
        LIMIT :limit
    """
    df = _df(session, sql, {"pid": project_id, "limit": limit})
    if not df.empty:
        df = df.iloc[::-1]  # reverse so oldest is on the left
    return df.to_dict(orient="records")
