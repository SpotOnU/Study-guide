"""Removing repeated slide clutter (such as copyright footers) from transcripts.

Professor Messer slides carry this footer on every page:

    https://ProfessorMesser.com © 2025 Messer Studios, LLC

It is noise for studying, so it is removed from transcripts and can never
become study material. OCR rarely reads it perfectly ("@" for "©", missing
"//", odd spacing, a different year, split over two lines, or glued onto the
end of a real line), so detection is deliberately tolerant:

1. Footer text is cut out of a line with forgiving patterns. If nothing
   meaningful is left, the whole line goes; if real content is left, the
   content is kept.
2. A whole line is also dropped if it is a close fuzzy match (after ignoring
   case, spacing, punctuation and the year) for the footer or one of its
   halves.

Only footer text is removed. Lines are never dropped just for being near the
bottom of a slide, and a generic line such as "Copyright law protects
software" is kept: the general rule only matches real copyright *notices*
(a © or "Copyright" followed by a year, or "All rights reserved").

You can add your own phrases in the "Ignore Text" window. Every change made
to existing transcripts is backed up first, so a cleanup can be undone.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from . import db
from .db import now_iso

# --------------------------------------------------------------------------
# Known footers
# --------------------------------------------------------------------------

KNOWN_FOOTERS = [
    "https://ProfessorMesser.com © 2025 Messer Studios, LLC",
]

# Forgiving patterns for the Professor Messer footer, tolerant of common OCR
# confusions: o/0, l/1/i, m/rn, "©" read as "@", "(c)", "c" or "e", etc.
_O = "[o0]"
_SEP = r"[\s.,·:;]*"
MESSER_URL = re.compile(
    r"(?:h\s*t\s*t\s*p\s*s?\s*[:;.]?\s*[/\\|l1i]{0,2}\s*[/\\|l1i]{0,2}\s*)?"  # https://
    r"(?:w\s*w\s*w\s*[.,]\s*)?"
    rf"pr{_O}f\s*e\s*s\s*s\s*{_O}\s*r\s*[-_]?\s*m\s*e\s*s\s*s\s*e\s*r"
    rf"{_SEP}c\s*{_O}\s*(?:m|rn)",
    re.IGNORECASE,
)
MESSER_COPYRIGHT = re.compile(
    r"(?:©|\(\s*c\s*\)|@|®|\bc\b|\be\b)?\s*"
    r"(?:(?:19|20)[0-9OoIl]{2}\s*[-–]?\s*(?:(?:19|20)[0-9OoIl]{2})?\s*[,.]?\s*)?"
    rf"m\s*e\s*s\s*s\s*e\s*r\s*s\s*t\s*u\s*d\s*[il1]\s*{_O}\s*s?"
    r"(?:\s*[,.]?\s*(?:l\s*\.?\s*l\s*\.?\s*c\.?|ll[cg]|l1c|1lc|ilc|lc))?",
    re.IGNORECASE,
)

# A real copyright notice: "© 2025", "(c) 2024", "Copyright 2023", "Copyright ©",
# "All rights reserved". The word "copyright" alone is NOT enough.
COPYRIGHT_NOTICE = re.compile(
    r"(?:©|\(\s*c\s*\))\s*(?:19|20)\d\d"
    r"|\bcopyright\s*(?:©|\(\s*c\s*\))?\s*(?:19|20)\d\d"
    r"|\bcopyright\s*(?:©|\(\s*c\s*\))"
    r"|\ball rights reserved\b",
    re.IGNORECASE,
)
MAX_NOTICE_WORDS = 14  # longer lines are probably real content, not a notice

FUZZY_THRESHOLD = 0.8
LEFTOVER = re.compile(r"[A-Za-z0-9]")

SETTING_BUILTIN = "ignore_builtin"
SETTING_PHRASES = "ignore_phrases"


def normalize(text: str) -> str:
    """Lower-case letters only, with digits collapsed to '#': ignores spacing,
    punctuation, OCR symbol noise and which year is printed."""
    text = text.lower().replace("©", "")
    text = re.sub(r"\d", "#", text)
    text = re.sub(r"#+", "#", text)
    return re.sub(r"[^a-z#]", "", text)


def _footer_targets() -> List[str]:
    targets = []
    for footer in KNOWN_FOOTERS:
        targets.append(normalize(footer))
        for part in re.split(r"©", footer):
            if part.strip():
                targets.append(normalize(part))
                targets.append(normalize(re.sub(r"https?://|www\.", "", part)))
    return [t for t in dict.fromkeys(targets) if len(t) >= 8]


FOOTER_TARGETS = _footer_targets()


def _strip_known_footer(line: str) -> str:
    """Cut known footer text out of a line, tidying the separators left behind."""
    stripped = MESSER_URL.sub(" ", line)
    stripped = MESSER_COPYRIGHT.sub(" ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped.rstrip(" |•·-–—,.;:").lstrip(" |,;:")


def is_footer_text(text: str) -> bool:
    """True if the text is (a fuzzy match for) a known footer or one of its parts."""
    norm = normalize(text)
    if len(norm) < 6:
        return False
    if not LEFTOVER.search(_strip_known_footer(text)) and norm:
        return True
    return any(SequenceMatcher(None, norm, t).ratio() >= FUZZY_THRESHOLD for t in FOOTER_TARGETS)


def contains_footer(text: str) -> bool:
    """True if any part of the text looks like footer material."""
    if MESSER_URL.search(text) or MESSER_COPYRIGHT.search(text):
        return True
    return any(is_footer_text(line) for line in text.splitlines())


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@dataclass
class Rules:
    builtin: bool = True  # known footers + copyright notices
    phrases: List[str] = field(default_factory=list)

    def clean_line(self, line: str) -> Optional[str]:
        """Return the cleaned line, or None if the whole line should go."""
        stripped = line.strip()
        if not stripped:
            return line
        if self.builtin:
            if is_footer_text(stripped):
                return None
            if MESSER_URL.search(stripped) or MESSER_COPYRIGHT.search(stripped):
                # footer text glued onto a real line: keep the real part
                without = _strip_known_footer(stripped)
                if not LEFTOVER.search(without):
                    return None
                stripped = without
            if COPYRIGHT_NOTICE.search(stripped) and len(stripped.split()) <= MAX_NOTICE_WORDS:
                return None
        norm = normalize(stripped)
        for phrase in self.phrases:
            p = normalize(phrase)
            if p and p in norm:
                return None
        return stripped if stripped != line.strip() else line

    def matches(self, line: str) -> bool:
        """True if the line would be removed entirely."""
        return line.strip() != "" and self.clean_line(line) is None


ALWAYS = Rules(builtin=True)  # used by the study-material generator regardless of settings


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
    """Return (cleaned text, list of removed or changed original lines)."""
    kept, removed = [], []
    for line in text.splitlines():
        cleaned = rules.clean_line(line)
        if cleaned is None:
            removed.append(line)
            continue
        if cleaned != line:
            removed.append(line)
        kept.append(cleaned)
    return "\n".join(kept).strip("\n"), removed


# --------------------------------------------------------------------------
# Cleaning saved transcripts (with backup and undo)
# --------------------------------------------------------------------------


def preview_all(conn: sqlite3.Connection, rules: Rules) -> List[Tuple[int, str, List[str]]]:
    """[(image_id, rel_path, removed lines)] for transcripts the rules would change."""
    out = []
    rows = conn.execute(
        "SELECT tr.image_id, tr.text, i.rel_path FROM transcripts tr "
        "JOIN images i ON i.id = tr.image_id ORDER BY i.rel_path COLLATE NOCASE"
    ).fetchall()
    for row in rows:
        _, removed = clean_text(row["text"], rules)
        if removed:
            out.append((row["image_id"], row["rel_path"], removed))
    return out


def count_affected(conn: sqlite3.Connection, rules: Rules) -> int:
    return len(preview_all(conn, rules))


def clean_all(conn: sqlite3.Connection, rules: Rules, reason: str = "cleanup") -> int:
    """Clean every saved transcript. The previous text is backed up first.

    Returns how many transcripts changed. Only footer/notice text is removed;
    everything else (including your own edits) stays.
    """
    batch = now_iso()
    changed = 0
    rows = conn.execute("SELECT image_id, text FROM transcripts").fetchall()
    with conn:
        for row in rows:
            cleaned, removed = clean_text(row["text"], rules)
            if not removed:
                continue
            conn.execute(
                "INSERT INTO transcript_history (image_id, text, saved_at, reason, batch) "
                "VALUES (?, ?, ?, ?, ?)",
                (row["image_id"], row["text"], now_iso(), reason, batch),
            )
            conn.execute(
                "UPDATE transcripts SET text = ?, updated_at = ? WHERE image_id = ?",
                (cleaned, now_iso(), row["image_id"]),
            )
            changed += 1
    return changed


def last_cleanup_batch(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute(
        "SELECT batch FROM transcript_history WHERE reason LIKE 'cleanup%' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["batch"] if row else None


def undo_last_cleanup(conn: sqlite3.Connection) -> int:
    """Put back the transcripts as they were before the most recent cleanup."""
    batch = last_cleanup_batch(conn)
    if batch is None:
        return 0
    rows = conn.execute(
        "SELECT id, image_id, text FROM transcript_history WHERE batch = ? AND reason LIKE 'cleanup%'",
        (batch,),
    ).fetchall()
    with conn:
        for row in rows:
            conn.execute(
                "UPDATE transcripts SET text = ?, updated_at = ? WHERE image_id = ?",
                (row["text"], now_iso(), row["image_id"]),
            )
            conn.execute("UPDATE transcript_history SET reason = 'cleanup-undone' WHERE id = ?", (row["id"],))
    return len(rows)
