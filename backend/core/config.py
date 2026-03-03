"""
backend/core/config.py
──────────────────────
Central settings object. All values are read from environment variables
(or a .env file in the project root). Import `settings` everywhere instead
of calling os.getenv() directly.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────
    database_url: str = "sqlite:///./jira_analytics.db"

    # ── Jira (mirrored from jira_sync.py so the API can trigger syncs) ────
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_story_points_field: str = "story_points"
    jira_ac_field: str = "customfield_10016"

    # ── API behaviour ─────────────────────────────────────────
    # Number of closed sprints to average for velocity
    velocity_window: int = 3
    # CORS origins allowed to hit the API (comma-separated in .env)
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached singleton – safe to call at module level."""
    return Settings()


# Convenience alias used throughout the app
settings = get_settings()
