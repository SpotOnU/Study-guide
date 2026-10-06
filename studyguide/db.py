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
    # 2: flashcards, review schedule, points and badges
    """
    -- Cards are tied to the slide they came from. They are never deleted:
    -- if the transcript changes so a card no longer applies, it is "retired"
    -- (hidden) and keeps its review history.
    CREATE TABLE cards (
        id          INTEGER PRIMARY KEY,
        image_id    INTEGER NOT NULL REFERENCES images(id),
        kind        TEXT NOT NULL,
        front       TEXT NOT NULL,
        back        TEXT NOT NULL,
        context     TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        generator   TEXT NOT NULL,
        position    INTEGER NOT NULL DEFAULT 0,
        retired     INTEGER NOT NULL DEFAULT 0,
        hidden      INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL,
        UNIQUE (image_id, fingerprint)
    );

    -- Review schedule for cards you have seen at least once.
    CREATE TABLE card_state (
        card_id       INTEGER PRIMARY KEY REFERENCES cards(id),
        due_at        TEXT NOT NULL,
        interval_days REAL NOT NULL,
        ease          REAL NOT NULL,
        reps          INTEGER NOT NULL,
        lapses        INTEGER NOT NULL,
        last_grade    TEXT NOT NULL,
        last_reviewed TEXT NOT NULL
    );

    CREATE TABLE review_log (
        id            INTEGER PRIMARY KEY,
        card_id       INTEGER NOT NULL REFERENCES cards(id),
        reviewed_at   TEXT NOT NULL,
        grade         TEXT NOT NULL,
        interval_days REAL NOT NULL
    );
    CREATE INDEX review_log_at ON review_log(reviewed_at);

    CREATE TABLE rounds (
        id          INTEGER PRIMARY KEY,
        kind        TEXT NOT NULL,
        topic_id    INTEGER REFERENCES topics(id),
        started_at  TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        total       INTEGER NOT NULL,
        correct     INTEGER NOT NULL,
        xp          INTEGER NOT NULL
    );

    CREATE TABLE xp_log (
        id       INTEGER PRIMARY KEY,
        at       TEXT NOT NULL,
        points   INTEGER NOT NULL,
        reason   TEXT NOT NULL,
        topic_id INTEGER REFERENCES topics(id)
    );

    CREATE TABLE badges (
        badge_id  TEXT PRIMARY KEY,
        earned_at TEXT NOT NULL
    );
    """,
]


def now_iso() -> str:
    return iso(datetime.now(timezone.utc))


def iso(moment: datetime) -> str:
    """Store times as UTC ISO strings so they sort and compare as text."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


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
