"""
backend/db/session.py
─────────────────────
SQLAlchemy engine setup and the get_db() FastAPI dependency that
provides a per-request session and guarantees it is closed afterwards.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────

_connect_args: dict = {}

# SQLite needs check_same_thread=False for FastAPI's threading model
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,   # recycle stale connections automatically
    echo=False,
    future=True,
)

# Enable WAL mode for SQLite (much better concurrent read performance)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    Yield a SQLAlchemy Session and guarantee it is closed when the
    request finishes (whether it succeeded or raised an exception).

    Usage in a route::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
