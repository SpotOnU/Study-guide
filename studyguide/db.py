"""SQLite storage for the library, transcripts and settings.

Schema changes are applied as numbered migrations so that future versions of
the app can add tables (questions, progress, ...) without losing existing data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

MIGRATIONS = [
    # 1: library, transcripts, settings
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE libraries (
        id        INTEGER PRIMARY KEY,
        root_path TEXT NOT NULL UNIQUE,
        added_at  TEXT NOT NULL
    );

    CREATE TABLE topics (
        id         INTEGER PRIMARY KEY,
        library_id INTEGER NOT NULL REFERENCES libraries(id),
        name       TEXT NOT NULL,
        present    INTEGER NOT NULL DEFAULT 1,
        first_seen TEXT NOT NULL,
        last_seen  TEXT NOT NULL,
        UNIQUE (library_id, name)
    );

    -- One row per PNG. Identified by its path relative to the study folder,
    -- so rescans keep the same id (and therefore transcripts and progress).
    CREATE TABLE images (
        id         INTEGER PRIMARY KEY,
        library_id INTEGER NOT NULL REFERENCES libraries(id),
        topic_id   INTEGER NOT NULL REFERENCES topics(id),
        rel_path   TEXT NOT NULL,
        size       INTEGER NOT NULL,
        mtime      REAL NOT NULL,
        sha256     TEXT NOT NULL,
        present    INTEGER NOT NULL DEFAULT 1,
        first_seen TEXT NOT NULL,
        last_seen  TEXT NOT NULL,
        UNIQUE (library_id, rel_path)
    );

    -- Editable transcript of one image. `ocr_text` keeps the last machine
    -- reading; `text` is what the user sees and edits.
    CREATE TABLE transcripts (
        image_id      INTEGER PRIMARY KEY REFERENCES images(id),
        text          TEXT NOT NULL DEFAULT '',
        ocr_text      TEXT,
        ocr_engine    TEXT,
        ocr_sha256    TEXT,
        edited        INTEGER NOT NULL DEFAULT 0,
        updated_at    TEXT NOT NULL
    );
    """,
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for index in range(version, len(MIGRATIONS)):
        with conn:
            conn.executescript(MIGRATIONS[index])
            conn.execute(f"PRAGMA user_version = {index + 1}")


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
