"""Removing repeated clutter (copyright footers, web addresses) from transcripts.

Slides often carry the same footer on every page, for example
"https://ProfessorMesser.com © 2025 Messer Studios, LLC". Those lines are
noise for studying, so whole lines that match are dropped from transcripts.

Two kinds of rules:
* built-in (can be switched off): lines containing a copyright notice, and
  lines that are only a web address
* your own phrases: any line containing one of them (ignoring case) is dropped

Only the visible transcript is cleaned. The raw OCR reading is kept as is.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Tuple

from . import db
from .db import now_iso

COPYRIGHT = re.compile(r"©|\(c\)\s*\d{4}|\bcopyright\b|\ball rights reserved\b", re.IGNORECASE)
URL_ONLY = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)

SETTING_BUILTIN = "ignore_builtin"
SETTING_PHRASES = "ignore_phrases"


@dataclass
class Rules:
    builtin: bool = True
    phrases: List[str] = field(default_factory=list)

    def matches(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if self.builtin and (COPYRIGHT.search(stripped) or URL_ONLY.match(stripped)):
            return True
        lower = stripped.lower()
        return any(p and p.lower() in lower for p in self.phrases)


def load_rules(conn: sqlite3.Connection) -> Rules:
    builtin = db.get_setting(conn, SETTING_BUILTIN)
    phrases = db.get_setting(conn, SETTING_PHRASES) or ""
    return Rules(
        builtin=builtin != "0",
        phrases=[p.strip() for p in phrases.splitlines() if p.strip()],
    )


def save_rules(conn: sqlite3.Connection, rules: Rules) -> None:
    db.set_setting(conn, SETTING_BUILTIN, "1" if rules.builtin else "0")
    db.set_setting(conn, SETTING_PHRASES, "\n".join(rules.phrases))


def clean_text(text: str, rules: Rules) -> Tuple[str, List[str]]:
    """Return (cleaned text, removed lines)."""
    kept, removed = [], []
    for line in text.splitlines():
        (removed if rules.matches(line) else kept).append(line)
    cleaned = "\n".join(kept).strip("\n")
    return cleaned, removed


def clean_all(conn: sqlite3.Connection, rules: Rules) -> int:
    """Remove matching lines from every saved transcript. Returns how many changed.

    Only whole matching lines are removed; everything else you typed stays.
    """
    changed = 0
    rows = conn.execute("SELECT image_id, text FROM transcripts").fetchall()
    with conn:
        for row in rows:
            cleaned, removed = clean_text(row["text"], rules)
            if removed:
                conn.execute(
                    "UPDATE transcripts SET text = ?, updated_at = ? WHERE image_id = ?",
                    (cleaned, now_iso(), row["image_id"]),
                )
                changed += 1
    return changed


def count_affected(conn: sqlite3.Connection, rules: Rules) -> int:
    return sum(
        1
        for row in conn.execute("SELECT text FROM transcripts")
        if clean_text(row["text"], rules)[1]
    )
