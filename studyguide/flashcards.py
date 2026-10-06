"""Flashcards: keeping cards in step with transcripts, picking rounds, and scheduling reviews.

Scheduling is a simplified spaced-repetition system. After you see a card you
choose one of three answers:

* again: you'll see it again in about 10 minutes
* good:  1 day, then 3 days, then the gap keeps growing
* easy:  a bigger jump
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from .db import iso, now_iso, parse_iso
from .generators import GenerationResult, Generator, SlideText, StudyItem, get_generator
from .generators.validate import legacy_card_problems

CURRENT_VERSION = 2  # cards made before this are from the old fragment-based generator
GRADES = ("again", "good", "easy")
RETRY_DELAY = timedelta(minutes=10)
START_EASE = 2.5
MIN_EASE = 1.3


def fingerprint(kind: str, concept: str, answer: str) -> str:
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    return hashlib.sha1(f"{kind}|{norm(concept)}|{norm(answer)}".encode()).hexdigest()


def card_details(card: sqlite3.Row) -> Dict:
    try:
        return json.loads(card["details"] or "{}")
    except (ValueError, TypeError):
        return {}


# --------------------------------------------------------------------------
# Keeping cards in step with transcripts
# --------------------------------------------------------------------------


@dataclass
class SyncResult:
    added: int = 0
    retired: int = 0
    restored: int = 0
    paused: int = 0  # old cards newly paused because they failed quality checks
    waiting: int = 0  # slides whose old cards are waiting for you to approve regenerating


def _topic_slides(conn: sqlite3.Connection, library_id: int, topic_id: Optional[int] = None):
    sql = (
        "SELECT i.id, i.rel_path, i.topic_id, t.name AS topic, COALESCE(tr.text, '') AS text "
        "FROM images i JOIN topics t ON t.id = i.topic_id "
        "LEFT JOIN transcripts tr ON tr.image_id = i.id "
        "WHERE i.library_id = ? AND i.present = 1 AND t.present = 1 "
    )
    args: list = [library_id]
    if topic_id is not None:
        sql += "AND i.topic_id = ? "
        args.append(topic_id)
    topics: Dict[int, List[SlideText]] = {}
    for r in conn.execute(sql + "ORDER BY i.rel_path COLLATE NOCASE", args):
        topics.setdefault(r["topic_id"], []).append(SlideText(r["id"], r["topic"], r["rel_path"], r["text"]))
    return topics


def _images_with_old_cards(conn: sqlite3.Connection, library_id: int) -> set:
    return {
        r[0] for r in conn.execute(
            "SELECT DISTINCT c.image_id FROM cards c JOIN images i ON i.id = c.image_id "
            "WHERE i.library_id = ? AND c.gen_version < ? AND c.retired = 0",
            (library_id, CURRENT_VERSION),
        )
    }


def check_old_cards(conn: sqlite3.Connection, library_id: int) -> int:
    """Pause cards from the old generator that fail the quality checks, so they are
    no longer presented as valid study material. Returns how many were newly paused."""
    rows = conn.execute(
        "SELECT c.id, c.front, c.back FROM cards c JOIN images i ON i.id = c.image_id "
        "WHERE i.library_id = ? AND c.gen_version < ? AND c.retired = 0 AND c.paused IS NULL",
        (library_id, CURRENT_VERSION),
    ).fetchall()
    paused = 0
    with conn:
        for r in rows:
            problems = legacy_card_problems(r["front"], r["back"])
            if problems:
                conn.execute("UPDATE cards SET paused = ? WHERE id = ?", ("; ".join(problems), r["id"]))
                paused += 1
    return paused


@dataclass
class OldCardsStatus:
    total: int  # old-generator cards still in your deck
    paused: int  # of those, kept out of rounds because they failed checks
    fragments: int  # paused for fragment/instruction wording like "Find the ___ you need"
    examples: List[sqlite3.Row]


def old_cards_status(conn: sqlite3.Connection, library_id: int) -> OldCardsStatus:
    base = ("FROM cards c JOIN images i ON i.id = c.image_id "
            "WHERE i.library_id = ? AND c.gen_version < ? AND c.retired = 0 ")
    args = (library_id, CURRENT_VERSION)
    total = conn.execute("SELECT COUNT(*) " + base, args).fetchone()[0]
    paused = conn.execute("SELECT COUNT(*) " + base + "AND c.paused IS NOT NULL", args).fetchone()[0]
    fragment_sql = "AND (c.paused LIKE '%fragment%' OR c.paused LIKE '%instruction%' OR c.paused LIKE '%vague%' OR c.paused LIKE '%footer%') "
    fragments = conn.execute("SELECT COUNT(*) " + base + fragment_sql, args).fetchone()[0]
    examples = conn.execute(
        "SELECT c.*, i.rel_path " + base + "AND c.paused IS NOT NULL "
        "ORDER BY (CASE WHEN c.paused LIKE '%fragment%' OR c.paused LIKE '%instruction%' THEN 0 ELSE 1 END), c.id "
        "LIMIT 6", args,
    ).fetchall()
    return OldCardsStatus(total, paused, fragments, examples)


def _store_items(conn: sqlite3.Connection, image_id: int, items: List[StudyItem], generator: Generator) -> SyncResult:
    existing = {
        r["fingerprint"]: r
        for r in conn.execute(
            "SELECT * FROM cards WHERE image_id = ? AND gen_version >= ?", (image_id, CURRENT_VERSION)
        )
    }
    result = SyncResult()
    keep = set()
    stamp = now_iso()
    with conn:
        for position, item in enumerate(items):
            fp = fingerprint(item.kind, item.concept, item.answer)
            if fp in keep:
                continue
            keep.add(fp)
            values = (item.kind, item.prompt, item.answer, item.slide_support, item.explanation,
                      json.dumps(item.details()), position)
            old = existing.get(fp)
            if old is None:
                conn.execute(
                    "INSERT INTO cards (kind, front, back, context, explanation, details, position, "
                    "image_id, fingerprint, generator, gen_version, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values + (image_id, fp, generator.name, generator.version, stamp),
                )
                result.added += 1
            else:
                if old["retired"]:
                    result.restored += 1
                conn.execute(
                    "UPDATE cards SET kind = ?, front = ?, back = ?, context = ?, explanation = ?, "
                    "details = ?, position = ?, retired = 0 WHERE id = ?",
                    values + (old["id"],),
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
    """Create study items for new or changed transcripts. Never deletes cards or history.

    Slides that still have cards from the old generator are left alone until
    you approve regenerating them (see ``regenerate_old_cards``); their
    failing cards are paused in the meantime.
    """
    generator = generator or get_generator()
    total = SyncResult(paused=check_old_cards(conn, library_id))
    waiting = _images_with_old_cards(conn, library_id)
    for slides in _topic_slides(conn, library_id, topic_id).values():
        ids = {s.image_id for s in slides}
        targets = ids - waiting
        total.waiting += len(ids & waiting)
        if not targets:
            continue
        generated = generator.generate_topic(slides, only_ids=targets)
        by_image: Dict[int, List[StudyItem]] = {}
        for item in generated.items:
            by_image.setdefault(item.image_id, []).append(item)
        for image_id in targets:
            r = _store_items(conn, image_id, by_image.get(image_id, []), generator)
            total.added += r.added
            total.retired += r.retired
            total.restored += r.restored
    return total


def preview_items(
    conn: sqlite3.Connection,
    library_id: int,
    topic_id: Optional[int] = None,
    generator: Optional[Generator] = None,
    only_waiting: bool = False,
) -> GenerationResult:
    """Generate items without saving anything (for previews)."""
    generator = generator or get_generator()
    waiting = _images_with_old_cards(conn, library_id) if only_waiting else None
    combined = GenerationResult()
    for slides in _topic_slides(conn, library_id, topic_id).values():
        only = {s.image_id for s in slides} & waiting if waiting is not None else None
        if only is not None and not only:
            continue
        r = generator.generate_topic(slides, only_ids=only)
        combined.items += r.items
        combined.rejected += r.rejected
        combined.skipped_slides += r.skipped_slides
    return combined


def regenerate_old_cards(conn: sqlite3.Connection, library_id: int, generator: Optional[Generator] = None) -> SyncResult:
    """Replace old-generator cards with new study items made from the same slides.

    Old cards are retired (hidden), not deleted, so their review history is kept.
    """
    with conn:
        cur = conn.execute(
            "UPDATE cards SET retired = 1 WHERE gen_version < ? AND retired = 0 AND image_id IN "
            "(SELECT id FROM images WHERE library_id = ?)",
            (CURRENT_VERSION, library_id),
        )
    result = sync_cards(conn, library_id, generator=generator)
    result.retired += cur.rowcount
    return result


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------

ACTIVE = (
    "FROM cards c JOIN images i ON i.id = c.image_id JOIN topics t ON t.id = i.topic_id "
    "LEFT JOIN card_state s ON s.card_id = c.id "
    "WHERE c.retired = 0 AND c.hidden = 0 AND c.paused IS NULL AND i.present = 1 AND t.present = 1 "
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
