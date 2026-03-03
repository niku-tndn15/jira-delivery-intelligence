"""
jira_sync.py
────────────
Authenticates with Jira Cloud via API token and syncs Projects, Sprints,
and Issues (with changelog) into the local PostgreSQL / SQLite database.

Usage
-----
    python jira_sync.py --project PLAT          # incremental sync
    python jira_sync.py --project PLAT --full   # full re-sync
    python jira_sync.py --all-projects          # sync every project in DB

Environment variables (.env)
------------------------------
    JIRA_BASE_URL   https://yourorg.atlassian.net
    JIRA_EMAIL      you@yourorg.com
    JIRA_API_TOKEN  <token from id.atlassian.com/manage-profile/security>
    DATABASE_URL    postgresql://user:pass@localhost:5432/jira_analytics
                    (or sqlite:///./jira_analytics.db for local dev)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

JIRA_BASE_URL  = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL     = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
DATABASE_URL   = os.getenv("DATABASE_URL", "sqlite:///./jira_analytics.db")

# Jira field IDs  – adjust if your instance uses a different custom-field ID
STORY_POINTS_FIELD  = os.getenv("JIRA_STORY_POINTS_FIELD",  "story_points")
ACCEPTANCE_CRITERIA_FIELD = os.getenv("JIRA_AC_FIELD", "customfield_10016")

PAGE_SIZE = 100   # max Jira allows per call


# ── HTTP client (shared, with auth + retries) ─────────────────────────────────

class JiraClient:
    """Thin wrapper around httpx for Jira REST v2/v3 / Agile v1."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=JIRA_BASE_URL,
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )

    # ── low-level ──────────────────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None) -> dict | list:
        """GET with exponential back-off on 429 / 5xx."""
        url = path if path.startswith("http") else path
        for attempt in range(5):
            r = self._client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = 2 ** attempt
                log.warning("Rate-limited – sleeping %ss", wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
        raise RuntimeError(f"Failed after retries: GET {path}")

    def paginate(self, path: str, key: str, params: dict | None = None):
        """Yield pages from a Jira REST endpoint that uses startAt / maxResults."""
        params = dict(params or {})
        params["maxResults"] = PAGE_SIZE
        params["startAt"]    = 0
        while True:
            data   = self.get(path, params)
            items  = data.get(key, [])
            yield from items
            total  = data.get("total", len(items))
            params["startAt"] += len(items)
            if params["startAt"] >= total or not items:
                break

    def paginate_agile(self, path: str, key: str, params: dict | None = None):
        """Same but for the Agile API (uses isLast instead of total)."""
        params = dict(params or {})
        params["maxResults"] = PAGE_SIZE
        params["startAt"]    = 0
        while True:
            data  = self.get(path, params)
            items = data.get(key, [])
            yield from items
            if data.get("isLast", True) or not items:
                break
            params["startAt"] += len(items)

    def paginate_jql(self, path: str, key: str, params: dict | None = None):
        """Yield pages from the new Jira search API that uses nextPageToken."""
        params = dict(params or {})
        params["maxResults"] = PAGE_SIZE
        
        while True:
            data  = self.get(path, params)
            items = data.get(key, [])
            yield from items
            
            # The new v3 API uses a token instead of startAt offsets
            next_token = data.get("nextPageToken")
            if not next_token or not items:
                break
            
            params["nextPageToken"] = next_token

    # ── high-level helpers ─────────────────────────────────────────────────

    def get_project(self, project_key: str) -> dict:
        return self.get(f"/rest/api/2/project/{project_key}")

    def get_boards(self, project_key: str) -> list[dict]:
        return list(
            self.paginate_agile(
                "/rest/agile/1.0/board",
                "values",
                {"projectKeyOrId": project_key, "type": "scrum"},
            )
        )

    def get_sprints(self, board_id: int) -> list[dict]:
        return list(
            self.paginate_agile(
                f"/rest/agile/1.0/board/{board_id}/sprint",
                "values",
            )
        )

    def get_sprint_issues(self, sprint_id: int) -> list[dict]:
        return list(
            self.paginate_agile(
                f"/rest/agile/1.0/sprint/{sprint_id}/issue",
                "issues",
                {"expand": "changelog", "fields": _issue_fields()},
            )
        )

    def get_issues(self, jql: str) -> list[dict]:
        return list(
            self.paginate_jql(
                "/rest/api/3/search/jql",
                "issues",
                {"jql": jql, "expand": "changelog", "fields": _issue_fields()},
            )
        )


def _issue_fields() -> str:
    return (
        "summary,description,issuetype,priority,status,assignee,reporter,"
        "created,updated,resolutiondate,duedate,timeoriginalestimate,"
        "timespent,timeestimate,parent,sprint,"
        f"{STORY_POINTS_FIELD},{ACCEPTANCE_CRITERIA_FIELD}"
    )


# ── Database helpers ───────────────────────────────────────────────────────────

def get_engine():
    return create_engine(DATABASE_URL, echo=False, future=True)


def upsert_project(session: Session, jira_data: dict) -> int:
    row = {
        "jira_key":        jira_data["key"],
        "name":            jira_data["name"],
        "description":     jira_data.get("description"),
        "lead_email":      (jira_data.get("lead") or {}).get("emailAddress"),
        "jira_project_id": str(jira_data["id"]),
        "synced_at":       _now(),
    }
    result = session.execute(
        text("""
            INSERT INTO projects (jira_key, name, description, lead_email,
                                  jira_project_id, synced_at)
            VALUES (:jira_key, :name, :description, :lead_email,
                    :jira_project_id, :synced_at)
            ON CONFLICT (jira_key) DO UPDATE SET
                name            = EXCLUDED.name,
                description     = EXCLUDED.description,
                lead_email      = EXCLUDED.lead_email,
                jira_project_id = EXCLUDED.jira_project_id,
                synced_at       = EXCLUDED.synced_at,
                updated_at      = NOW()
            RETURNING id
        """),
        row,
    )
    project_id = result.scalar_one()
    session.commit()
    log.info("Project upserted: %s (id=%s)", row["jira_key"], project_id)
    return project_id


def upsert_sprint(session: Session, sprint: dict, project_id: int) -> int:
    row = {
        "jira_sprint_id": sprint["id"],
        "project_id":     project_id,
        "name":           sprint["name"],
        "state":          sprint["state"],
        "goal":           sprint.get("goal"),
        "start_date":     _parse_dt(sprint.get("startDate")),
        "end_date":       _parse_dt(sprint.get("endDate")),
        "complete_date":  _parse_dt(sprint.get("completeDate")),
        "synced_at":      _now(),
    }
    result = session.execute(
        text("""
            INSERT INTO sprints (jira_sprint_id, project_id, name, state, goal,
                                 start_date, end_date, complete_date, synced_at)
            VALUES (:jira_sprint_id, :project_id, :name, :state, :goal,
                    :start_date, :end_date, :complete_date, :synced_at)
            ON CONFLICT (jira_sprint_id) DO UPDATE SET
                name          = EXCLUDED.name,
                state         = EXCLUDED.state,
                goal          = EXCLUDED.goal,
                start_date    = EXCLUDED.start_date,
                end_date      = EXCLUDED.end_date,
                complete_date = EXCLUDED.complete_date,
                synced_at     = EXCLUDED.synced_at,
                updated_at    = NOW()
            RETURNING id
        """),
        row,
    )
    sprint_id = result.scalar_one()
    session.commit()
    return sprint_id


def upsert_issue(
    session: Session,
    issue: dict,
    project_id: int,
    sprint_id: int | None,
    sprint_start: datetime | None,
) -> int:
    fields = issue["fields"]
    sp     = _story_points(fields)
    ac     = _acceptance_criteria(fields)

    in_progress_at, done_at = _extract_transition_dates(issue.get("changelog", {}))

    created_jira = _parse_dt(fields.get("created"))
    added_mid    = (
        bool(sprint_start and created_jira and created_jira > sprint_start)
    )

    row = {
        "jira_issue_id":     issue["key"],
        "project_id":        project_id,
        "sprint_id":         sprint_id,
        "parent_issue_id":   None,   # resolved in a second pass if needed
        "issue_type":        (fields.get("issuetype") or {}).get("name"),
        "priority":          (fields.get("priority")  or {}).get("name"),
        "status":            (fields.get("status")    or {}).get("name"),
        "status_category":   ((fields.get("status") or {}).get("statusCategory") or {}).get("name"),
        "summary":           fields["summary"],
        "description":       _extract_text(fields.get("description")),
        "acceptance_criteria": ac,
        "story_points":      sp,
        "original_estimate": fields.get("timeoriginalestimate"),
        "time_spent":        fields.get("timespent"),
        "remaining_estimate":fields.get("timeestimate"),
        "assignee_email":    (fields.get("assignee") or {}).get("emailAddress"),
        "reporter_email":    (fields.get("reporter")  or {}).get("emailAddress"),
        "created_at_jira":   created_jira,
        "updated_at_jira":   _parse_dt(fields.get("updated")),
        "in_progress_at":    in_progress_at,
        "done_at":           done_at,
        "due_date":          fields.get("duedate"),
        "added_mid_sprint":  added_mid,
        "synced_at":         _now(),
    }

    result = session.execute(
        text("""
            INSERT INTO issues (
                jira_issue_id, project_id, sprint_id, parent_issue_id,
                issue_type, priority, status, status_category, summary,
                description, acceptance_criteria, story_points,
                original_estimate, time_spent, remaining_estimate,
                assignee_email, reporter_email,
                created_at_jira, updated_at_jira,
                in_progress_at, done_at, due_date,
                added_mid_sprint, synced_at
            ) VALUES (
                :jira_issue_id, :project_id, :sprint_id, :parent_issue_id,
                :issue_type, :priority, :status, :status_category, :summary,
                :description, :acceptance_criteria, :story_points,
                :original_estimate, :time_spent, :remaining_estimate,
                :assignee_email, :reporter_email,
                :created_at_jira, :updated_at_jira,
                :in_progress_at, :done_at, :due_date,
                :added_mid_sprint, :synced_at
            )
            ON CONFLICT (jira_issue_id) DO UPDATE SET
                sprint_id           = EXCLUDED.sprint_id,
                status              = EXCLUDED.status,
                status_category     = EXCLUDED.status_category,
                story_points        = EXCLUDED.story_points,
                acceptance_criteria = EXCLUDED.acceptance_criteria,
                in_progress_at      = COALESCE(issues.in_progress_at, EXCLUDED.in_progress_at),
                done_at             = COALESCE(issues.done_at, EXCLUDED.done_at),
                time_spent          = EXCLUDED.time_spent,
                remaining_estimate  = EXCLUDED.remaining_estimate,
                added_mid_sprint    = EXCLUDED.added_mid_sprint,
                synced_at           = EXCLUDED.synced_at,
                updated_at          = NOW()
            RETURNING id
        """),
        row,
    )
    issue_db_id = result.scalar_one()

    # Persist changelog as status history
    _upsert_status_history(session, issue_db_id, issue.get("changelog", {}))

    session.commit()
    return issue_db_id


def _upsert_status_history(session: Session, issue_db_id: int, changelog: dict):
    for history in changelog.get("histories", []):
        for item in history.get("items", []):
            if item.get("field") != "status":
                continue
            session.execute(
                text("""
                    INSERT INTO issue_status_history
                        (issue_id, from_status, to_status, transitioned_at, author_email)
                    VALUES
                        (:issue_id, :from_status, :to_status, :transitioned_at, :author_email)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "issue_id":       issue_db_id,
                    "from_status":    item.get("fromString"),
                    "to_status":      item["toString"],
                    "transitioned_at": _parse_dt(history["created"]),
                    "author_email":   (history.get("author") or {}).get("emailAddress"),
                },
            )


# ── Main sync orchestration ────────────────────────────────────────────────────

class JiraSyncer:
    def __init__(self) -> None:
        self.client = JiraClient()
        self.engine = get_engine()

    def sync_project(self, project_key: str, full: bool = False) -> None:
        log.info("══ Syncing project: %s (full=%s)", project_key, full)

        jira_proj = self.client.get_project(project_key)

        with Session(self.engine) as session:
            project_id = upsert_project(session, jira_proj)
            sync_log_id = self._start_log(session, project_id, "full" if full else "incremental")

        boards = self.client.get_boards(project_key)
        if not boards:
            log.warning("No Scrum board found for %s – skipping sprint sync", project_key)
            board_id = None
        else:
            board_id = boards[0]["id"]
            log.info("Using board id=%s (%s)", board_id, boards[0]["name"])
            with Session(self.engine) as session:
                session.execute(
                    text("UPDATE projects SET board_id = :bid WHERE id = :pid"),
                    {"bid": board_id, "pid": project_id},
                )
                session.commit()

        issues_count  = 0
        sprints_count = 0

        if board_id:
            sprints = self.client.get_sprints(board_id)
            log.info("Found %d sprints", len(sprints))

            for sprint in sprints:
                sprint_start = _parse_dt(sprint.get("startDate"))
                with Session(self.engine) as session:
                    sprint_db_id = upsert_sprint(session, sprint, project_id)
                sprints_count += 1

                sprint_issues = self.client.get_sprint_issues(sprint["id"])
                log.info(
                    "  Sprint '%s' (%s) – %d issues",
                    sprint["name"], sprint["state"], len(sprint_issues),
                )
                for issue in sprint_issues:
                    with Session(self.engine) as session:
                        upsert_issue(session, issue, project_id, sprint_db_id, sprint_start)
                    issues_count += 1

        # Also sync backlog (issues not in any sprint)
        jql = f"project = {project_key} AND sprint is EMPTY ORDER BY created DESC"
        backlog = self.client.get_issues(jql)
        log.info("Backlog (no sprint): %d issues", len(backlog))
        for issue in backlog:
            with Session(self.engine) as session:
                upsert_issue(session, issue, project_id, None, None)
            issues_count += 1

        with Session(self.engine) as session:
            self._finish_log(session, sync_log_id, issues_count, sprints_count)
            
        
        # ── AUTOMATED STORY POINT CALCULATION ────────────────────────────────
        print("🧮 Running automated Story Point calculations for new tickets...")
        
        calc_sql = text("""
            UPDATE issues 
            SET story_points = GREATEST(ROUND(COALESCE(NULLIF(time_spent, 0), NULLIF(original_estimate, 0), 9600) / 28800.0 * 3, 1), 1)
            WHERE story_points IS NULL OR time_spent > 0;
        """)
        
        with Session(self.engine) as session:
            session.execute(calc_sql)
            session.commit()
        # ─────────────────────────────────────────────────────────────────────
        

        log.info(
            "✔ Done: %d issues, %d sprints synced for %s",
            issues_count, sprints_count, project_key,
        )

    # ── sync-log helpers ──────────────────────────────────────────────────

    def _start_log(self, session: Session, project_id: int, sync_type: str) -> int:
        result = session.execute(
            text("""
                INSERT INTO sync_log (project_id, sync_type, status)
                VALUES (:pid, :stype, 'running')
                RETURNING id
            """),
            {"pid": project_id, "stype": sync_type},
        )
        sync_id = result.scalar_one()
        session.commit()
        return sync_id

    def _finish_log(
        self, session: Session, sync_log_id: int, issues: int, sprints: int
    ) -> None:
        session.execute(
            text("""
                UPDATE sync_log SET
                    status         = 'success',
                    issues_synced  = :issues,
                    sprints_synced = :sprints,
                    finished_at    = NOW()
                WHERE id = :sid
            """),
            {"issues": issues, "sprints": sprints, "sid": sync_log_id},
        )
        session.commit()


# ── Utility helpers ────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None

def _extract_text(obj: Any) -> str:
    """Recursively extract plain text from Atlassian Document Format (ADF)."""
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        text_val = obj.get("text", "")
        if "content" in obj:
            text_val += " " + " ".join(_extract_text(c) for c in obj.get("content", []))
        return text_val.strip()
    if isinstance(obj, list):
        return " ".join(_extract_text(item) for item in obj)
    return str(obj)

def _story_points(fields: dict) -> float | None:
    val = fields.get(STORY_POINTS_FIELD) or fields.get("story_points")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def _acceptance_criteria(fields: dict) -> str | None:
    """Pull AC from a dedicated custom field or try to extract it from description."""
    ac = fields.get(ACCEPTANCE_CRITERIA_FIELD)
    if ac:
        return _extract_text(ac)
        
    desc_str = _extract_text(fields.get("description"))
    if not desc_str:
        return None
        
    lower = desc_str.lower()
    for marker in ("acceptance criteria", "acceptance criterion", "ac:", "given ", "scenario:"):
        idx = lower.find(marker)
        if idx != -1:
            return desc_str[idx:].strip()
    return None

def _extract_transition_dates(
    changelog: dict,
) -> tuple[datetime | None, datetime | None]:
    """Return (first_in_progress_at, first_done_at) from changelog."""
    in_progress_at: datetime | None = None
    done_at: datetime | None = None

    for history in changelog.get("histories", []):
        for item in history.get("items", []):
            if item.get("field") != "status":
                continue
            ts  = _parse_dt(history.get("created"))
            to  = (item.get("toString") or "").lower()
            if "in progress" in to and in_progress_at is None:
                in_progress_at = ts
            if to in ("done", "closed", "resolved") and done_at is None:
                done_at = ts

    return in_progress_at, done_at

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync Jira data into local DB")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", metavar="KEY", help="Jira project key, e.g. PLAT")
    group.add_argument("--all-projects", action="store_true")
    parser.add_argument("--full", action="store_true", help="Full re-sync (ignore last sync timestamp)")
    args = parser.parse_args()

    syncer = JiraSyncer()

    if args.project:
        syncer.sync_project(args.project.upper(), full=args.full)
    else:
        engine = get_engine()
        with Session(engine) as session:
            keys = [r[0] for r in session.execute(text("SELECT jira_key FROM projects")).fetchall()]
        log.info("Syncing %d projects: %s", len(keys), keys)
        for key in keys:
            try:
                syncer.sync_project(key, full=args.full)
            except Exception as exc:
                log.error("Failed to sync %s: %s", key, exc)

if __name__ == "__main__":
    main()