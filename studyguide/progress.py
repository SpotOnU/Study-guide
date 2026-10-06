"""Points, levels, streaks and badges.

Everything here is encouraging: you earn points for trying, never lose them,
and a streak survives until the end of the day after you last studied.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .db import iso, parse_iso

XP_CORRECT = 10
XP_TRY = 2  # still learning: you get points for showing up
XP_ROUND_DONE = 5
XP_PERFECT_BONUS = 20
LEVEL_STEP = 50  # level n starts at LEVEL_STEP * (n-1)^2 XP

BADGES: Dict[str, Tuple[str, str, str]] = {
    # id: (emoji, name, how to earn it)
    "first_round": ("🌱", "First Steps", "Finish your first round"),
    "perfect_round": ("💯", "Flawless", "Get every card right in a round of 5 or more"),
    "streak_3": ("🔥", "On a Roll", "Study 3 days in a row"),
    "streak_7": ("🚀", "Week Warrior", "Study 7 days in a row"),
    "cards_50": ("🃏", "Card Shark", "Review 50 cards"),
    "cards_250": ("🧠", "Big Brain", "Review 250 cards"),
    "topic_star": ("⭐", "Topic Star", "Know every card in a topic (at least 5 cards)"),
    "comeback": ("💪", "Comeback Kid", "Get a card right that you missed before"),
}


def local_now() -> datetime:
    return datetime.now().astimezone()


def add_xp(conn, points: int, reason: str, topic_id: Optional[int] = None, now: Optional[datetime] = None) -> None:
    with conn:
        conn.execute(
            "INSERT INTO xp_log (at, points, reason, topic_id) VALUES (?, ?, ?, ?)",
            (iso(now or local_now()), points, reason, topic_id),
        )


def total_xp(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(points), 0) FROM xp_log").fetchone()[0]


@dataclass
class Level:
    level: int
    into_level: int  # XP earned since this level started
    needed: int  # XP between this level and the next


def level_for(xp: int) -> Level:
    level = int(math.isqrt(max(xp, 0) // LEVEL_STEP)) + 1
    start = LEVEL_STEP * (level - 1) ** 2
    nxt = LEVEL_STEP * level**2
    return Level(level, xp - start, nxt - start)


def study_dates(conn) -> List[date]:
    rows = conn.execute("SELECT reviewed_at FROM review_log").fetchall()
    return sorted({parse_iso(r[0]).astimezone(local_now().tzinfo).date() for r in rows})


def streaks(conn, today: Optional[date] = None) -> Tuple[int, int]:
    """(current streak, best streak) in days."""
    today = today or local_now().date()
    days = study_dates(conn)
    if not days:
        return 0, 0
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        best = max(best, run)
    # current streak counts back from today, or from yesterday if not studied yet today
    day_set = set(days)
    anchor = today if today in day_set else today - timedelta(days=1)
    current = 0
    while anchor in day_set:
        current += 1
        anchor -= timedelta(days=1)
    return current, best


def studied_today(conn, today: Optional[date] = None) -> bool:
    today = today or local_now().date()
    return today in set(study_dates(conn))


def record_round(conn, kind: str, topic_id: Optional[int], started: datetime, finished: datetime,
                 total: int, correct: int, xp: int) -> None:
    with conn:
        conn.execute(
            "INSERT INTO rounds (kind, topic_id, started_at, finished_at, total, correct, xp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, topic_id, iso(started), iso(finished), total, correct, xp),
        )


def earned_badges(conn) -> Dict[str, str]:
    return {r["badge_id"]: r["earned_at"] for r in conn.execute("SELECT * FROM badges")}


def _qualifies(conn) -> List[str]:
    got = []
    if conn.execute("SELECT 1 FROM rounds LIMIT 1").fetchone():
        got.append("first_round")
    if conn.execute("SELECT 1 FROM rounds WHERE total >= 5 AND correct = total LIMIT 1").fetchone():
        got.append("perfect_round")
    _, best = streaks(conn)
    if best >= 3:
        got.append("streak_3")
    if best >= 7:
        got.append("streak_7")
    reviews = conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0]
    if reviews >= 50:
        got.append("cards_50")
    if reviews >= 250:
        got.append("cards_250")
    star = conn.execute(
        "SELECT i.topic_id FROM cards c JOIN images i ON i.id = c.image_id "
        "LEFT JOIN card_state s ON s.card_id = c.id "
        "WHERE c.retired = 0 AND c.hidden = 0 AND c.paused IS NULL AND i.present = 1 "
        "GROUP BY i.topic_id HAVING COUNT(*) >= 5 "
        "AND SUM(CASE WHEN s.reps >= 1 AND s.last_grade != 'again' THEN 1 ELSE 0 END) = COUNT(*) "
        "LIMIT 1"
    ).fetchone()
    if star:
        got.append("topic_star")
    comeback = conn.execute(
        "SELECT 1 FROM review_log a JOIN review_log b ON a.card_id = b.card_id "
        "WHERE a.grade = 'again' AND b.grade != 'again' AND b.id > a.id LIMIT 1"
    ).fetchone()
    if comeback:
        got.append("comeback")
    return got


def check_badges(conn, now: Optional[datetime] = None) -> List[str]:
    """Award any badges that are newly earned and return their ids."""
    have = earned_badges(conn)
    new = [b for b in _qualifies(conn) if b not in have]
    with conn:
        for badge in new:
            conn.execute(
                "INSERT INTO badges (badge_id, earned_at) VALUES (?, ?)", (badge, iso(now or local_now()))
            )
    return new
