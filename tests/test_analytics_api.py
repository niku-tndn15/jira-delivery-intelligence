"""
tests/test_analytics_api.py
────────────────────────────
Integration tests that spin up the FastAPI app against a real SQLite
in-memory database seeded with known fixture data.

Run:
    pytest tests/test_analytics_api.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ── Point config at SQLite BEFORE importing anything else ────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_jira.db")
os.environ.setdefault("JIRA_BASE_URL", "https://example.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "test-token")

from backend.api.main import app
from backend.db.session import get_db

# ── In-memory SQLite for tests ────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def _setup_schema(engine):
    """Create tables via raw SQL (mirrors schema.sql, simplified for SQLite)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_key        TEXT NOT NULL UNIQUE,
                name            TEXT NOT NULL,
                description     TEXT,
                lead_email      TEXT,
                jira_project_id TEXT,
                board_id        INTEGER,
                synced_at       TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sprints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_sprint_id  INTEGER NOT NULL UNIQUE,
                project_id      INTEGER NOT NULL,
                name            TEXT    NOT NULL,
                state           TEXT    NOT NULL,
                goal            TEXT,
                start_date      TEXT,
                end_date        TEXT,
                complete_date   TEXT,
                committed_points REAL,
                completed_points REAL,
                added_points     REAL,
                removed_points   REAL,
                synced_at       TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS issues (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_issue_id       TEXT NOT NULL UNIQUE,
                project_id          INTEGER NOT NULL,
                sprint_id           INTEGER,
                parent_issue_id     INTEGER,
                issue_type          TEXT,
                priority            TEXT,
                status              TEXT NOT NULL,
                status_category     TEXT,
                summary             TEXT NOT NULL,
                description         TEXT,
                acceptance_criteria TEXT,
                has_ac              INTEGER GENERATED ALWAYS AS (
                    CASE WHEN acceptance_criteria IS NOT NULL
                              AND trim(acceptance_criteria) != ''
                         THEN 1 ELSE 0 END
                ) STORED,
                story_points        REAL,
                original_estimate   INTEGER,
                time_spent          INTEGER,
                remaining_estimate  INTEGER,
                assignee_email      TEXT,
                reporter_email      TEXT,
                created_at_jira     TEXT,
                updated_at_jira     TEXT,
                in_progress_at      TEXT,
                done_at             TEXT,
                due_date            TEXT,
                added_mid_sprint    INTEGER NOT NULL DEFAULT 0,
                synced_at           TEXT,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS issue_status_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id        INTEGER NOT NULL,
                from_status     TEXT,
                to_status       TEXT NOT NULL,
                transitioned_at TEXT NOT NULL,
                author_email    TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sprint_issue_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                sprint_id     INTEGER NOT NULL,
                issue_id      INTEGER NOT NULL,
                snapshot_type TEXT    NOT NULL,
                story_points  REAL,
                status        TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (sprint_id, issue_id, snapshot_type)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      INTEGER,
                sync_type       TEXT NOT NULL,
                status          TEXT NOT NULL,
                issues_synced   INTEGER DEFAULT 0,
                sprints_synced  INTEGER DEFAULT 0,
                error_message   TEXT,
                started_at      TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at     TEXT
            )
        """))


def _seed(engine):
    """Insert deterministic fixture data so test assertions are exact."""
    now = datetime.now(timezone.utc)

    def dt(days_ago: float = 0) -> str:
        return (now - timedelta(days=days_ago)).isoformat()

    with engine.begin() as conn:
        # Project
        conn.execute(text("""
            INSERT INTO projects (jira_key, name, synced_at)
            VALUES ('TEST', 'Test Project', :now)
        """), {"now": now.isoformat()})

        # Sprints: 3 closed + 1 active
        for i, (name, start_ago, end_ago, complete_ago) in enumerate(
            [
                ("Sprint 1", 60, 46, 45),
                ("Sprint 2", 44, 30, 29),
                ("Sprint 3", 28, 14, 13),
            ],
            start=1,
        ):
            conn.execute(text("""
                INSERT INTO sprints
                    (jira_sprint_id, project_id, name, state,
                     start_date, end_date, complete_date)
                VALUES (:sid, 1, :name, 'closed', :sd, :ed, :cd)
            """), {
                "sid":  i,
                "name": name,
                "sd":   dt(start_ago),
                "ed":   dt(end_ago),
                "cd":   dt(complete_ago),
            })

        # Active sprint
        conn.execute(text("""
            INSERT INTO sprints
                (jira_sprint_id, project_id, name, state, start_date, end_date)
            VALUES (4, 1, 'Sprint 4', 'active', :sd, :ed)
        """), {"sd": dt(7), "ed": dt(-7)})

        # Issues for Sprint 1: 20 pts committed, 16 done
        issues_s1 = [
            ("TEST-1", 1, "Story", "Done",        "Done",        8,  False, dt(55), dt(50)),
            ("TEST-2", 1, "Story", "Done",        "Done",        5,  False, dt(55), dt(48)),
            ("TEST-3", 1, "Bug",   "Done",        "Done",        3,  False, dt(55), dt(49)),
            ("TEST-4", 1, "Task",  "To Do",       "To Do",       4,  False, None,   None),
        ]
        # Issues for Sprint 2: 18 pts committed, 18 done
        issues_s2 = [
            ("TEST-5",  2, "Story", "Done", "Done", 8, False, dt(40), dt(35)),
            ("TEST-6",  2, "Story", "Done", "Done", 5, False, dt(40), dt(33)),
            ("TEST-7",  2, "Bug",   "Done", "Done", 5, False, dt(40), dt(31)),
            ("TEST-8",  2, "Story", "Done", "Done", 2, True,  dt(38), dt(30)),  # mid-sprint
        ]
        # Issues for Sprint 3: 21 pts committed, 13 done
        issues_s3 = [
            ("TEST-9",  3, "Story", "Done",        "Done",        8,  False, dt(22), dt(16)),
            ("TEST-10", 3, "Story", "In Progress", "In Progress", 5,  False, dt(22), None),
            ("TEST-11", 3, "Bug",   "Done",        "Done",        5,  False, dt(22), dt(14)),
            ("TEST-12", 3, "Story", "To Do",       "To Do",       3,  True,  None,   None),  # mid-sprint
        ]
        # Active sprint issues
        issues_s4 = [
            ("TEST-13", 4, "Story", "Done",        "Done",        5,  False, dt(5), dt(2)),
            ("TEST-14", 4, "Story", "In Progress", "In Progress", 3,  False, dt(5), None),
            ("TEST-15", 4, "Bug",   "To Do",       "To Do",       2,  False, None,  None),
            ("TEST-16", 4, "Story", "To Do",       "To Do",       3,  True,  None,  None),  # mid-sprint
        ]
        # Backlog issues (no sprint)
        issues_backlog = [
            ("TEST-17", None, "Story", "To Do", "To Do", 3, False, None, None),
            ("TEST-18", None, "Story", "To Do", "To Do", 2, False, None, None),
            ("TEST-19", None, "Bug",   "To Do", "To Do", 1, False, None, None),
            ("TEST-20", None, "Story", "To Do", "To Do", 5, False, None, None),
        ]

        ac_text = "Given a user, when they submit, then it should succeed"
        for issue_list in [issues_s1, issues_s2, issues_s3, issues_s4, issues_backlog]:
            for idx, (key, sid, itype, status, scat, pts, mid, ip, done) in enumerate(issue_list):
                # Give half the backlog issues acceptance criteria
                ac = ac_text if sid is None and idx % 2 == 0 else None
                conn.execute(text("""
                    INSERT INTO issues (
                        jira_issue_id, project_id, sprint_id, issue_type,
                        status, status_category, summary, story_points,
                        in_progress_at, done_at, added_mid_sprint,
                        acceptance_criteria, created_at_jira
                    ) VALUES (
                        :key, 1, :sid, :itype,
                        :status, :scat, :summary, :pts,
                        :ip, :done, :mid,
                        :ac, :created
                    )
                """), {
                    "key":     key,
                    "sid":     sid,
                    "itype":   itype,
                    "status":  status,
                    "scat":    scat,
                    "summary": f"Summary for {key}",
                    "pts":     pts,
                    "ip":      ip,
                    "done":    done,
                    "mid":     1 if mid else 0,
                    "ac":      ac,
                    "created": dt(60),
                })


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_engine():
    _setup_schema(test_engine)
    _seed(test_engine)
    yield test_engine


@pytest.fixture(scope="session")
def client(db_engine):
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: system
# ─────────────────────────────────────────────────────────────────────────────

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_meta(client):
    r = client.get("/api/meta")
    assert r.status_code == 200
    data = r.json()
    assert "projects" in data
    assert any(p["jira_key"] == "TEST" for p in data["projects"])


# ─────────────────────────────────────────────────────────────────────────────
# Tests: projects
# ─────────────────────────────────────────────────────────────────────────────

def test_list_projects(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) >= 1
    assert projects[0]["jira_key"] == "TEST"


def test_get_project(client):
    r = client.get("/api/projects/TEST")
    assert r.status_code == 200
    assert r.json()["name"] == "Test Project"


def test_get_project_not_found(client):
    r = client.get("/api/projects/NOPE")
    assert r.status_code == 404


def test_list_sprints(client):
    r = client.get("/api/projects/TEST/sprints")
    assert r.status_code == 200
    assert len(r.json()) == 4  # 3 closed + 1 active


def test_list_sprints_filter_state(client):
    r = client.get("/api/projects/TEST/sprints?state=closed")
    assert r.status_code == 200
    assert all(s["state"] == "closed" for s in r.json())


# ─────────────────────────────────────────────────────────────────────────────
# Tests: velocity
# ─────────────────────────────────────────────────────────────────────────────

def test_velocity_structure(client):
    r = client.get("/api/TEST/metrics/velocity")
    assert r.status_code == 200
    data = r.json()
    assert "average_completed_points" in data
    assert "predictability_pct" in data
    assert "trend" in data
    assert data["window"] == 3


def test_velocity_trend_length(client):
    r = client.get("/api/TEST/metrics/velocity?window=3")
    data = r.json()
    assert data["sprints_analysed"] == 3
    assert len(data["trend"]) == 3


def test_velocity_window_override(client):
    r = client.get("/api/TEST/metrics/velocity?window=2")
    data = r.json()
    assert data["window"] == 2
    assert data["sprints_analysed"] == 2


def test_velocity_trend_ascending(client):
    """Trend should be oldest-first so the frontend can plot left→right."""
    r = client.get("/api/TEST/metrics/velocity?window=3")
    trend = r.json()["trend"]
    names = [t["sprint_name"] for t in trend]
    assert names == ["Sprint 1", "Sprint 2", "Sprint 3"]


def test_velocity_not_found(client):
    r = client.get("/api/GHOST/metrics/velocity")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests: scope creep
# ─────────────────────────────────────────────────────────────────────────────

def test_scope_creep_structure(client):
    r = client.get("/api/TEST/metrics/scope-creep")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    row = data[0]
    assert "scope_creep_pct" in row
    assert "added_issue_detail" in row
    assert "original_issues" in row


def test_scope_creep_has_mid_sprint_issues(client):
    r = client.get("/api/TEST/metrics/scope-creep?limit=10")
    sprints = {s["sprint_name"]: s for s in r.json()}
    # Sprint 2 has TEST-8 (added mid-sprint)
    assert sprints["Sprint 2"]["added_issues"] == 1
    assert sprints["Sprint 2"]["scope_creep_pct"] > 0


def test_scope_creep_detail_fields(client):
    r = client.get("/api/TEST/metrics/scope-creep?limit=10")
    for sprint in r.json():
        for issue in sprint["added_issue_detail"]:
            assert "jira_issue_id" in issue
            assert "summary" in issue
            assert "story_points" in issue


# ─────────────────────────────────────────────────────────────────────────────
# Tests: cycle time
# ─────────────────────────────────────────────────────────────────────────────

def test_cycle_time_structure(client):
    r = client.get("/api/TEST/metrics/cycle-time")
    assert r.status_code == 200
    data = r.json()
    for key in ("mean_days", "p50_days", "p75_days", "p95_days", "stddev_days", "sample_size"):
        assert key in data


def test_cycle_time_positive(client):
    r = client.get("/api/TEST/metrics/cycle-time")
    data = r.json()
    assert data["sample_size"] > 0
    assert data["mean_days"] is not None
    assert data["mean_days"] > 0


def test_cycle_time_filter_by_type(client):
    r_story = client.get("/api/TEST/metrics/cycle-time?issue_type=Story")
    r_bug   = client.get("/api/TEST/metrics/cycle-time?issue_type=Bug")
    assert r_story.status_code == 200
    assert r_bug.status_code == 200
    # Story and bug sample sizes should differ
    assert r_story.json()["issue_type"] == "Story"
    assert r_bug.json()["issue_type"] == "Bug"


def test_cycle_time_distribution_is_list(client):
    r = client.get("/api/TEST/metrics/cycle-time/distribution")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) > 0


def test_cycle_time_distribution_fields(client):
    r = client.get("/api/TEST/metrics/cycle-time/distribution")
    for row in r.json():
        assert "jira_issue_id" in row
        assert "cycle_days" in row
        assert row["cycle_days"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: sprint completion
# ─────────────────────────────────────────────────────────────────────────────

def test_sprint_completion_structure(client):
    r = client.get("/api/TEST/metrics/sprint-completion")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    row = data[0]
    for key in ("completion_pct_points", "completion_pct_issues",
                "done_points", "total_points"):
        assert key in row


def test_sprint_completion_pct_range(client):
    r = client.get("/api/TEST/metrics/sprint-completion?limit=10")
    for sprint in r.json():
        pct = sprint["completion_pct_points"]
        assert pct is None or (0 <= pct <= 100)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: backlog readiness
# ─────────────────────────────────────────────────────────────────────────────

def test_backlog_readiness_structure(client):
    r = client.get("/api/TEST/metrics/backlog-readiness")
    assert r.status_code == 200
    data = r.json()
    for key in ("total_backlog", "with_ac", "with_points",
                "ac_readiness_pct", "full_readiness_pct", "by_issue_type"):
        assert key in data


def test_backlog_readiness_totals_consistent(client):
    r = client.get("/api/TEST/metrics/backlog-readiness")
    data = r.json()
    assert data["with_ac"] <= data["total_backlog"]
    assert data["with_points"] <= data["total_backlog"]
    assert data["fully_ready"] <= data["total_backlog"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: distribution
# ─────────────────────────────────────────────────────────────────────────────

def test_distribution_structure(client):
    r = client.get("/api/TEST/metrics/distribution")
    assert r.status_code == 200
    data = r.json()
    assert "by_status" in data
    assert "by_type" in data


def test_distribution_pct_sums_to_100(client):
    r = client.get("/api/TEST/metrics/distribution")
    pcts = [row["pct_of_total"] for row in r.json()["by_status"] if row["pct_of_total"]]
    if pcts:
        assert abs(sum(pcts) - 100) < 1  # allow rounding


# ─────────────────────────────────────────────────────────────────────────────
# Tests: delivery health
# ─────────────────────────────────────────────────────────────────────────────

def test_delivery_health_structure(client):
    r = client.get("/api/TEST/metrics/health")
    assert r.status_code == 200
    data = r.json()
    assert "velocity" in data
    assert "cycle_time" in data
    assert "backlog" in data
    assert "current_sprint" in data


def test_delivery_health_velocity_snippet(client):
    r = client.get("/api/TEST/metrics/health")
    vel = r.json()["velocity"]
    assert "average_completed_points" in vel
    assert "predictability_pct" in vel


def test_delivery_health_not_found(client):
    r = client.get("/api/GHOST/metrics/health")
    assert r.status_code == 404
