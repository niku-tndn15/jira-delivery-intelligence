"""
backend/api/projects.py
────────────────────────
GET /api/projects          – list all synced projects
GET /api/projects/{key}    – get a single project by Jira key
GET /api/projects/{key}/sprints – list sprints for a project
"""

import sys
import os
# Ensure FastAPI can find your scripts folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from scripts.jira_sync import JiraSyncer


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.schemas import ProjectOut, SprintOut
from backend.db.session import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    """Return every project that has been synced from Jira."""
    rows = db.execute(
        text("""
            SELECT id, jira_key, name, description, lead_email, board_id,
                   synced_at::text
            FROM projects
            ORDER BY name
        """)
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{project_key}", response_model=ProjectOut)
def get_project(project_key: str, db: Session = Depends(get_db)):
    """Return a single project by its Jira key (e.g. PLAT)."""
    row = db.execute(
        text("""
            SELECT id, jira_key, name, description, lead_email, board_id,
                   synced_at::text
            FROM projects
            WHERE jira_key = :key
        """),
        {"key": project_key.upper()},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Project '{project_key}' not found")
    return dict(row._mapping)


@router.get("/{project_key}/sprints", response_model=list[SprintOut])
def list_sprints(
    project_key: str,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """
    List sprints for a project.
    Optional ?state=active|closed|future filter.
    """
    project = db.execute(
        text("SELECT id FROM projects WHERE jira_key = :key"),
        {"key": project_key.upper()},
    ).fetchone()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_key}' not found")

    sql = """
        SELECT id, jira_sprint_id, name, state, goal,
               start_date::text, end_date::text, complete_date::text
        FROM sprints
        WHERE project_id = :pid
          AND (:state IS NULL OR state = :state)
        ORDER BY start_date DESC
    """
    rows = db.execute(text(sql), {"pid": project.id, "state": state}).fetchall()
    return [dict(r._mapping) for r in rows]



@router.post("/{project_key}/sync", summary="Trigger manual Jira sync")
def sync_project_data(project_key: str):
    """Pulls the latest data directly from Jira for this project."""
    try:
        syncer = JiraSyncer()
        # Because your script uses the updated_at timestamp, 
        # this will be blazing fast—it only downloads tickets changed in the last 15 mins!
        syncer.sync_project(project_key.upper())
        return {"status": "success", "message": f"Successfully synced {project_key}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")