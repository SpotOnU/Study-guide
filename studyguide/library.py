"""Scanning the study folder and keeping the library in sync.

Rules:
* Each non-hidden subfolder of the study folder is a topic.
* Every .png inside a topic folder (including nested folders) belongs to it.
* Source images are only ever opened for reading. Nothing here writes,
  moves, renames or deletes anything inside the study folder.
* Rescanning never deletes data. Images that disappear are marked "missing"
  and keep their transcripts; if they come back they are restored.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .db import now_iso

IMAGE_SUFFIXES = {".png"}


@dataclass
class FoundImage:
    topic: str
    rel_path: str  # POSIX-style path relative to the study folder
    path: Path
    size: int
    mtime: float


@dataclass
class ScanResult:
    added: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    restored: List[str] = field(default_factory=list)
    unchanged: int = 0
    topics_added: List[str] = field(default_factory=list)
    loose_root_images: int = 0  # PNGs directly in the study folder (not in a topic)

    def summary(self) -> str:
        parts = [
            f"{len(self.added)} new",
            f"{len(self.changed)} changed",
            f"{len(self.restored)} restored",
            f"{len(self.missing)} missing",
            f"{self.unchanged} unchanged",
        ]
        text = "Scan complete: " + ", ".join(parts) + "."
        if self.loose_root_images:
            text += (
                f" {self.loose_root_images} PNG(s) sit directly in the study folder"
                " and were skipped. Put them in a topic subfolder to include them."
            )
        return text


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def _is_image(name: str) -> bool:
    return not _is_hidden(name) and Path(name).suffix.lower() in IMAGE_SUFFIXES


def find_images(root: Path) -> tuple[List[FoundImage], List[str], int]:
    """Walk the study folder (read-only). Returns (images, topic names, loose root PNG count)."""
    root = Path(root)
    images: List[FoundImage] = []
    topics: List[str] = []
    loose = 0
    for entry in sorted(os.scandir(root), key=lambda e: e.name.lower()):
        if _is_hidden(entry.name):
            continue
        if entry.is_file() and _is_image(entry.name):
            loose += 1
            continue
        if not entry.is_dir():
            continue
        topics.append(entry.name)
        for dirpath, dirnames, filenames in os.walk(entry.path):
            dirnames[:] = sorted(d for d in dirnames if not _is_hidden(d))
            for name in sorted(filenames, key=str.lower):
                if not _is_image(name):
                    continue
                path = Path(dirpath) / name
                stat = path.stat()
                images.append(
                    FoundImage(
                        topic=entry.name,
                        rel_path=path.relative_to(root).as_posix(),
                        path=path,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                    )
                )
    return images, topics, loose


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:  # read-only
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Libraries (one per chosen study folder)
# --------------------------------------------------------------------------


def get_or_create_library(conn: sqlite3.Connection, root: Path) -> int:
    root_str = str(Path(root).expanduser().resolve())
    row = conn.execute("SELECT id FROM libraries WHERE root_path = ?", (root_str,)).fetchone()
    if row:
        return row["id"]
    with conn:
        cur = conn.execute(
            "INSERT INTO libraries (root_path, added_at) VALUES (?, ?)", (root_str, now_iso())
        )
    return cur.lastrowid


def library_root(conn: sqlite3.Connection, library_id: int) -> Path:
    row = conn.execute("SELECT root_path FROM libraries WHERE id = ?", (library_id,)).fetchone()
    return Path(row["root_path"])


def scan_library(conn: sqlite3.Connection, library_id: int) -> ScanResult:
    """Bring the database in line with what is currently in the study folder."""
    root = library_root(conn, library_id)
    if not root.is_dir():
        raise FileNotFoundError(f"Study folder not found: {root}")

    found, topic_names, loose = find_images(root)
    result = ScanResult(loose_root_images=loose)
    stamp = now_iso()

    existing_topics: Dict[str, sqlite3.Row] = {
        r["name"]: r
        for r in conn.execute("SELECT * FROM topics WHERE library_id = ?", (library_id,))
    }
    existing_images: Dict[str, sqlite3.Row] = {
        r["rel_path"]: r
        for r in conn.execute("SELECT * FROM images WHERE library_id = ?", (library_id,))
    }

    with conn:
        topic_ids: Dict[str, int] = {}
        for name in topic_names:
            row = existing_topics.get(name)
            if row is None:
                cur = conn.execute(
                    "INSERT INTO topics (library_id, name, present, first_seen, last_seen) "
                    "VALUES (?, ?, 1, ?, ?)",
                    (library_id, name, stamp, stamp),
                )
                topic_ids[name] = cur.lastrowid
                result.topics_added.append(name)
            else:
                conn.execute(
                    "UPDATE topics SET present = 1, last_seen = ? WHERE id = ?", (stamp, row["id"])
                )
                topic_ids[name] = row["id"]
        for name, row in existing_topics.items():
            if name not in topic_ids:
                conn.execute("UPDATE topics SET present = 0 WHERE id = ?", (row["id"],))

        seen = set()
        for img in found:
            seen.add(img.rel_path)
            row = existing_images.get(img.rel_path)
            if row is None:
                conn.execute(
                    "INSERT INTO images (library_id, topic_id, rel_path, size, mtime, sha256, "
                    "present, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        library_id,
                        topic_ids[img.topic],
                        img.rel_path,
                        img.size,
                        img.mtime,
                        file_sha256(img.path),
                        stamp,
                        stamp,
                    ),
                )
                result.added.append(img.rel_path)
                continue

            sha = row["sha256"]
            if img.size != row["size"] or img.mtime != row["mtime"]:
                sha = file_sha256(img.path)
            if not row["present"]:
                result.restored.append(img.rel_path)
            elif sha != row["sha256"]:
                result.changed.append(img.rel_path)
            else:
                result.unchanged += 1
            conn.execute(
                "UPDATE images SET topic_id = ?, size = ?, mtime = ?, sha256 = ?, present = 1, "
                "last_seen = ? WHERE id = ?",
                (topic_ids[img.topic], img.size, img.mtime, sha, stamp, row["id"]),
            )

        for rel_path, row in existing_images.items():
            if rel_path not in seen and row["present"]:
                conn.execute("UPDATE images SET present = 0 WHERE id = ?", (row["id"],))
                result.missing.append(rel_path)

    return result


# --------------------------------------------------------------------------
# Queries used by the UI
# --------------------------------------------------------------------------


def list_topics(conn: sqlite3.Connection, library_id: int, include_missing: bool = False):
    sql = (
        "SELECT t.id, t.name, t.present, "
        "  SUM(CASE WHEN i.present = 1 THEN 1 ELSE 0 END) AS image_count, "
        "  SUM(CASE WHEN i.present = 1 AND tr.text IS NOT NULL AND tr.text != '' "
        "      THEN 1 ELSE 0 END) AS transcribed_count "
        "FROM topics t "
        "LEFT JOIN images i ON i.topic_id = t.id "
        "LEFT JOIN transcripts tr ON tr.image_id = i.id "
        "WHERE t.library_id = ? " + ("" if include_missing else "AND t.present = 1 ") +
        "GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
    )
    return conn.execute(sql, (library_id,)).fetchall()


def list_images(conn: sqlite3.Connection, topic_id: int, include_missing: bool = False):
    sql = (
        "SELECT i.*, tr.text AS transcript, tr.edited AS edited, tr.ocr_sha256 AS ocr_sha256 "
        "FROM images i LEFT JOIN transcripts tr ON tr.image_id = i.id "
        "WHERE i.topic_id = ? " + ("" if include_missing else "AND i.present = 1 ") +
        "ORDER BY i.rel_path COLLATE NOCASE"
    )
    return conn.execute(sql, (topic_id,)).fetchall()


def get_image(conn: sqlite3.Connection, image_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT i.*, t.name AS topic_name, l.root_path AS root_path "
        "FROM images i JOIN topics t ON t.id = i.topic_id "
        "JOIN libraries l ON l.id = i.library_id WHERE i.id = ?",
        (image_id,),
    ).fetchone()


def image_path(conn: sqlite3.Connection, image_id: int) -> Path:
    row = get_image(conn, image_id)
    return Path(row["root_path"]) / row["rel_path"]


def images_needing_ocr(conn: sqlite3.Connection, library_id: int) -> List[sqlite3.Row]:
    """Present images that have never been read, or whose file changed since the last read."""
    return conn.execute(
        "SELECT i.id, i.rel_path, i.sha256 FROM images i "
        "LEFT JOIN transcripts tr ON tr.image_id = i.id "
        "WHERE i.library_id = ? AND i.present = 1 "
        "AND (tr.image_id IS NULL OR tr.ocr_sha256 IS NULL OR tr.ocr_sha256 != i.sha256) "
        "ORDER BY i.rel_path COLLATE NOCASE",
        (library_id,),
    ).fetchall()
