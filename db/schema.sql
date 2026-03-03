-- ============================================================
-- Product Requirements & Delivery Analytics Platform
-- Database Schema
-- ============================================================

-- ── Projects ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id              SERIAL PRIMARY KEY,
    jira_key        VARCHAR(50)  NOT NULL UNIQUE,   -- e.g. "PLAT", "SHOP"
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    lead_email      VARCHAR(255),
    jira_project_id VARCHAR(50),                     -- numeric ID from Jira
    board_id        INTEGER,                          -- Scrum/Kanban board ID
    synced_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Sprints ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sprints (
    id              SERIAL PRIMARY KEY,
    jira_sprint_id  INTEGER      NOT NULL UNIQUE,
    project_id      INTEGER      NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    state           VARCHAR(20)  NOT NULL CHECK (state IN ('future', 'active', 'closed')),
    goal            TEXT,
    start_date      TIMESTAMPTZ,
    end_date        TIMESTAMPTZ,
    complete_date   TIMESTAMPTZ,
    -- Snapshot counters (populated after sprint closes)
    committed_points INTEGER,
    completed_points INTEGER,
    added_points     INTEGER,     -- scope creep: points added after sprint start
    removed_points   INTEGER,
    synced_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sprints_project ON sprints(project_id);
CREATE INDEX idx_sprints_state   ON sprints(state);

-- ── Issues ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS issues (
    id                  SERIAL PRIMARY KEY,
    jira_issue_id       VARCHAR(50)  NOT NULL UNIQUE,   -- "PLAT-123"
    project_id          INTEGER      NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sprint_id           INTEGER      REFERENCES sprints(id) ON DELETE SET NULL,
    parent_issue_id     INTEGER      REFERENCES issues(id) ON DELETE SET NULL,

    -- Classification
    issue_type          VARCHAR(50),    -- Story, Bug, Task, Epic, Sub-task
    priority            VARCHAR(20),    -- Highest, High, Medium, Low, Lowest
    status              VARCHAR(100)    NOT NULL,
    status_category     VARCHAR(50),    -- To Do | In Progress | Done

    -- Content
    summary             VARCHAR(500)    NOT NULL,
    description         TEXT,
    acceptance_criteria TEXT,           -- extracted from description or custom field
    has_ac              BOOLEAN GENERATED ALWAYS AS (
                            acceptance_criteria IS NOT NULL
                            AND trim(acceptance_criteria) <> ''
                        ) STORED,

    -- Estimation
    story_points        NUMERIC(6,1),
    original_estimate   INTEGER,        -- seconds
    time_spent          INTEGER,        -- seconds
    remaining_estimate  INTEGER,        -- seconds

    -- People
    assignee_email      VARCHAR(255),
    reporter_email      VARCHAR(255),

    -- Dates (key for cycle time)
    created_at_jira     TIMESTAMPTZ,
    updated_at_jira     TIMESTAMPTZ,
    in_progress_at      TIMESTAMPTZ,    -- first transition TO "In Progress"
    done_at             TIMESTAMPTZ,    -- first transition TO "Done"
    due_date            DATE,

    -- Scope-creep flag: was this issue added AFTER the sprint started?
    added_mid_sprint    BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Sync bookkeeping
    synced_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_issues_project        ON issues(project_id);
CREATE INDEX idx_issues_sprint         ON issues(sprint_id);
CREATE INDEX idx_issues_status         ON issues(status_category);
CREATE INDEX idx_issues_type           ON issues(issue_type);
CREATE INDEX idx_issues_in_progress_at ON issues(in_progress_at);
CREATE INDEX idx_issues_done_at        ON issues(done_at);

-- ── Issue Status History ─────────────────────────────────────
-- Every status transition captured from the Jira changelog.
-- Used to calculate accurate cycle time and lead time.
CREATE TABLE IF NOT EXISTS issue_status_history (
    id              SERIAL PRIMARY KEY,
    issue_id        INTEGER      NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    from_status     VARCHAR(100),
    to_status       VARCHAR(100) NOT NULL,
    transitioned_at TIMESTAMPTZ  NOT NULL,
    author_email    VARCHAR(255),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_history_issue ON issue_status_history(issue_id);
CREATE INDEX idx_history_ts    ON issue_status_history(transitioned_at);

-- ── Sprint Issue Snapshots ────────────────────────────────────
-- Records which issues were IN a sprint at sprint-start vs. sprint-close.
-- Enables accurate scope-creep and completion-rate reporting.
CREATE TABLE IF NOT EXISTS sprint_issue_snapshots (
    id              SERIAL PRIMARY KEY,
    sprint_id       INTEGER      NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
    issue_id        INTEGER      NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    snapshot_type   VARCHAR(20)  NOT NULL CHECK (snapshot_type IN ('start', 'end')),
    story_points    NUMERIC(6,1),
    status          VARCHAR(100),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (sprint_id, issue_id, snapshot_type)
);

CREATE INDEX idx_snapshots_sprint ON sprint_issue_snapshots(sprint_id);

-- ── Sync Log ─────────────────────────────────────────────────
-- Audit trail for every sync run; useful for debugging and scheduling.
CREATE TABLE IF NOT EXISTS sync_log (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    sync_type       VARCHAR(50)  NOT NULL,   -- 'full' | 'incremental' | 'sprint'
    status          VARCHAR(20)  NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    issues_synced   INTEGER      DEFAULT 0,
    sprints_synced  INTEGER      DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

-- ── Utility: auto-update updated_at ─────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sprints_updated_at
    BEFORE UPDATE ON sprints
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_issues_updated_at
    BEFORE UPDATE ON issues
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
