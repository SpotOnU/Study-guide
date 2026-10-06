"""Flashcards: keeping cards in step with transcripts, picking rounds, and scheduling reviews.

Scheduling is a simplified spaced-repetition system. After you see a card you
choose one of three answers:

* again: you'll see it again in about 10 minutes
* good:  1 day, then 3 days, then the gap keeps growing
* easy:  a bigger jump
"""

from __future__ import annotations

import hashlib
import random
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from .db import iso, now_iso, parse_iso
from .generators import Generator, SlideText, get_generator

GRADES = ("again", "good", "easy")
RETRY_DELAY = timedelta(minutes=10)
START_EASE = 2.5
MIN_EASE = 1.3


def fingerprint(kind: str, back: str, context: str) -> str:
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    return hashlib.sha1(f"{kind}|{norm(back)}|{norm(context)}".encode()).hexdigest()


# --------------------------------------------------------------------------
# Keeping cards in step with transcripts
# --------------------------------------------------------------------------


@dataclass
class SyncResult:
    added: int = 0
    retired: int = 0
    restored: int = 0


def sync_image(conn: sqlite3.Connection, image_id: int, generator: Generator) -> SyncResult:
    row = conn.execute(
        "SELECT i.id, i.rel_path, t.name AS topic, tr.text FROM images i "
        "JOIN topics t ON t.id = i.topic_id "
        "LEFT JOIN transcripts tr ON tr.image_id = i.id WHERE i.id = ?",
        (image_id,),
    ).fetchone()
    drafts = generator.flashcards(
        SlideText(row["id"], row["topic"], row["rel_path"], row["text"] or "")
    )
    existing = {
        r["fingerprint"]: r
        for r in conn.execute("SELECT * FROM cards WHERE image_id = ?", (image_id,))
    }
    result = SyncResult()
    keep = set()
    stamp = now_iso()
    with conn:
        for position, draft in enumerate(drafts):
            fp = fingerprint(draft.kind, draft.back, draft.context)
            if fp in keep:
                continue
            keep.add(fp)
            old = existing.get(fp)
            if old is None:
                conn.execute(
                    "INSERT INTO cards (image_id, kind, front, back, context, fingerprint, "
                    "generator, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (image_id, draft.kind, draft.front, draft.back, draft.context, fp,
                     generator.name, position, stamp),
                )
                result.added += 1
            else:
                if old["retired"]:
                    result.restored += 1
                conn.execute(
                    "UPDATE cards SET front = ?, back = ?, context = ?, position = ?, retired = 0 "
                    "WHERE id = ?",
                    (draft.front, draft.back, draft.context, position, old["id"]),
                )
        for fp, old in existing.items():
            if fp not in keep and not old["retired"]:
                conn.execute("UPDATE cards SET retired = 1 WHERE id = ?", (old["id"],))
                result.retired += 1
    return result


def sync_cards(
    conn: sqlite3.Connection,
    library_id: int,
    topic_id: Optional[int] = None,
    generator: Optional[Generator] = None,
) -> SyncResult:
    """Create cards for new or changed transcripts. Never deletes cards or history."""
    generator = generator or get_generator()
    sql = "SELECT id FROM images WHERE library_id = ? AND present = 1"
    args: list = [library_id]
    if topic_id is not None:
        sql += " AND topic_id = ?"
        args.append(topic_id)
    total = SyncResult()
    for row in conn.execute(sql, args).fetchall():
        r = sync_image(conn, row["id"], generator)
        total.added += r.added
        total.retired += r.retired
        total.restored += r.restored
    return total


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------

ACTIVE = (
    "FROM cards c JOIN images i ON i.id = c.image_id JOIN topics t ON t.id = i.topic_id "
    "LEFT JOIN card_state s ON s.card_id = c.id "
    "WHERE c.retired = 0 AND c.hidden = 0 AND i.present = 1 AND t.present = 1 "
    "AND i.library_id = ? "
)


def topic_overview(conn: sqlite3.Connection, library_id: int, now: Optional[datetime] = None):
    """Per topic: total cards, new (never seen), due now, and learned (seen and not due)."""
    now_s = iso(now or datetime.now().astimezone())
    return conn.execute(
        "SELECT t.id AS topic_id, t.name, COUNT(c.id) AS total, "
        "  SUM(CASE WHEN s.card_id IS NULL THEN 1 ELSE 0 END) AS new, "
        "  SUM(CASE WHEN s.due_at <= ? THEN 1 ELSE 0 END) AS due, "
        "  SUM(CASE WHEN s.due_at > ? THEN 1 ELSE 0 END) AS learned "
        + ACTIVE + "GROUP BY t.id ORDER BY t.name COLLATE NOCASE",
        (now_s, now_s, library_id),
    ).fetchall()


def get_card(conn: sqlite3.Connection, card_id: int) -> sqlite3.Row:
    return conn.execute(
        "SELECT c.*, i.rel_path, i.topic_id, t.name AS topic_name, l.root_path, "
        "s.due_at, s.interval_days, s.reps, s.last_grade "
        "FROM cards c JOIN images i ON i.id = c.image_id JOIN topics t ON t.id = i.topic_id "
        "JOIN libraries l ON l.id = i.library_id "
        "LEFT JOIN card_state s ON s.card_id = c.id WHERE c.id = ?",
        (card_id,),
    ).fetchone()


def build_round(
    conn: sqlite3.Connection,
    library_id: int,
    topic_id: Optional[int] = None,
    now: Optional[datetime] = None,
    size: int = 10,
    new_limit: int = 5,
    rng: Optional[random.Random] = None,
) -> List[int]:
    """Pick card ids for a short round: cards due for review first, then a few new ones.

    Two cards made from the same slide line (e.g. a definition and its
    reverse) never appear in the same round, so one can't give away the other.
    """
    rng = rng or random.Random()
    now_s = iso(now or datetime.now().astimezone())
    topic_sql, args = ("AND i.topic_id = ? ", [library_id, topic_id]) if topic_id else ("", [library_id])
    due = conn.execute(
        "SELECT c.id, c.image_id, c.context " + ACTIVE + topic_sql
        + "AND s.due_at <= ? ORDER BY s.due_at",
        args + [now_s],
    ).fetchall()
    new = conn.execute(
        "SELECT c.id, c.image_id, c.context " + ACTIVE + topic_sql
        + "AND s.card_id IS NULL ORDER BY t.name COLLATE NOCASE, i.rel_path COLLATE NOCASE, c.position",
        args,
    ).fetchall()

    chosen: List[int] = []
    used_lines = set()

    def take(rows: Sequence[sqlite3.Row], limit: int) -> None:
        count = 0
        for r in rows:
            if len(chosen) >= size or count >= limit:
                return
            key = (r["image_id"], r["context"].lower())
            if key in used_lines:
                continue
            used_lines.add(key)
            chosen.append(r["id"])
            count += 1

    take(due, size)
    take(new, new_limit if due else size)
    rng.shuffle(chosen)
    return chosen


def next_due_at(conn: sqlite3.Connection, library_id: int, topic_id: Optional[int] = None) -> Optional[datetime]:
    sql = "SELECT MIN(s.due_at) AS due " + ACTIVE
    args: list = [library_id]
    if topic_id:
        sql += "AND i.topic_id = ? "
        args.append(topic_id)
    row = conn.execute(sql, args).fetchone()
    return parse_iso(row["due"]) if row and row["due"] else None


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------


def schedule(state: Optional[Dict], grade: str, now: datetime) -> Dict:
    """Pure function: the next review state after answering a card."""
    if grade not in GRADES:
        raise ValueError(f"Unknown grade {grade!r}")
    ease = state["ease"] if state else START_EASE
    interval = state["interval_days"] if state else 0.0
    reps = state["reps"] if state else 0
    lapses = state["lapses"] if state else 0

    if grade == "again":
        if reps > 0:
            lapses += 1
        reps = 0
        interval = 0.0
        ease = max(MIN_EASE, ease - 0.2)
        due = now + RETRY_DELAY
    else:
        if grade == "good":
            interval = 1.0 if reps == 0 else 3.0 if reps == 1 else round(interval * ease, 1)
        else:  # easy
            interval = 3.0 if reps == 0 else 6.0 if reps == 1 else round(interval * ease * 1.3, 1)
            ease += 0.15
        reps += 1
        due = now + timedelta(days=interval)
    return {
        "due_at": iso(due),
        "interval_days": interval,
        "ease": round(ease, 2),
        "reps": reps,
        "lapses": lapses,
        "last_grade": grade,
        "last_reviewed": iso(now),
    }


def grade_card(conn: sqlite3.Connection, card_id: int, grade: str, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now().astimezone()
    row = conn.execute("SELECT * FROM card_state WHERE card_id = ?", (card_id,)).fetchone()
    new = schedule(dict(row) if row else None, grade, now)
    with conn:
        conn.execute(
            "INSERT INTO card_state (card_id, due_at, interval_days, ease, reps, lapses, "
            "last_grade, last_reviewed) VALUES (:card_id, :due_at, :interval_days, :ease, :reps, "
            ":lapses, :last_grade, :last_reviewed) ON CONFLICT(card_id) DO UPDATE SET "
            "due_at = excluded.due_at, interval_days = excluded.interval_days, ease = excluded.ease, "
            "reps = excluded.reps, lapses = excluded.lapses, last_grade = excluded.last_grade, "
            "last_reviewed = excluded.last_reviewed",
            dict(new, card_id=card_id),
        )
        conn.execute(
            "INSERT INTO review_log (card_id, reviewed_at, grade, interval_days) VALUES (?, ?, ?, ?)",
            (card_id, iso(now), grade, new["interval_days"]),
        )
    return new


def hide_card(conn: sqlite3.Connection, card_id: int, hidden: bool = True) -> None:
    """Hide a card that isn't useful. It can be brought back; nothing is deleted."""
    with conn:
        conn.execute("UPDATE cards SET hidden = ? WHERE id = ?", (1 if hidden else 0, card_id))


def describe_interval(days: float) -> str:
    if days <= 0:
        return "in a few minutes"
    if days < 1.5:
        return "tomorrow"
    if days < 30:
        return f"in {round(days)} days"
    return f"in about {round(days / 30)} month(s)"
