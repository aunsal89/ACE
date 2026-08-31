"""SQLite Database connection manager and schema initializer."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Optional
from contextlib import contextmanager

SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


def get_db_path(custom_path: Optional[Path | str] = None) -> Path:
    """Determine and return the target SQLite database path."""
    if custom_path:
        path = Path(custom_path).expanduser().resolve()
    else:
        # Default database location
        path = Path("/home/nsl/Portfolio/career-engine/data/career_engine.db").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_connection(db_path: Optional[Path | str] = None, timeout: float = 30.0) -> sqlite3.Connection:
    """Create a robust SQLite connection with WAL mode and foreign key enforcement."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path), timeout=timeout, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def get_db(db_path: Optional[Path | str] = None):
    """Context manager for transactional SQLite operations with auto-commit/rollback."""
    conn = create_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Initialize the SQLite database schema if not already present."""
    if not SCHEMA_SQL_PATH.exists():
        raise FileNotFoundError(f"Schema SQL file not found at {SCHEMA_SQL_PATH}")

    with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_db(db_path) as conn:
        conn.executescript(schema_sql)
