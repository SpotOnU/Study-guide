"""Editable transcripts of slide images.

A transcript has two texts:
* ``ocr_text`` is the last thing the OCR engine read from the image.
* ``text`` is what you see and edit, and what study materials will use.

Once you edit a transcript by hand, re-running OCR never overwrites your
text. It only updates ``ocr_text``, unless you explicitly ask to replace it.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from .db import now_iso


def get_transcript(conn: sqlite3.Connection, image_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM transcripts WHERE image_id = ?", (image_id,)).fetchone()


def save_transcript(conn: sqlite3.Connection, image_id: int, text: str) -> None:
    """Save a manual edit."""
    with conn:
        conn.execute(
            "INSERT INTO transcripts (image_id, text, edited, updated_at) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(image_id) DO UPDATE SET text = excluded.text, edited = 1, "
            "updated_at = excluded.updated_at",
            (image_id, text, now_iso()),
        )


def apply_ocr(
    conn: sqlite3.Connection,
    image_id: int,
    ocr_text: str,
    engine: str,
    image_sha256: str,
    replace_edits: bool = False,
) -> bool:
    """Store an OCR result. Returns True if the visible text was replaced.

    Hand-edited transcripts are kept unless ``replace_edits`` is True.
    """
    existing = get_transcript(conn, image_id)
    stamp = now_iso()
    with conn:
        if existing is None:
            conn.execute(
                "INSERT INTO transcripts (image_id, text, ocr_text, ocr_engine, ocr_sha256, "
                "edited, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (image_id, ocr_text, ocr_text, engine, image_sha256, stamp),
            )
            return True
        if existing["edited"] and not replace_edits:
            conn.execute(
                "UPDATE transcripts SET ocr_text = ?, ocr_engine = ?, ocr_sha256 = ?, "
                "updated_at = ? WHERE image_id = ?",
                (ocr_text, engine, image_sha256, stamp, image_id),
            )
            return False
        conn.execute(
            "UPDATE transcripts SET text = ?, ocr_text = ?, ocr_engine = ?, ocr_sha256 = ?, "
            "edited = 0, updated_at = ? WHERE image_id = ?",
            (ocr_text, ocr_text, engine, image_sha256, stamp, image_id),
        )
        return True
