"""Preview the questions the generator would make from your real transcripts.

Read-only: it opens the app's database in read-only mode, saves nothing and
never touches your images. Run it from the project folder:

    .venv/bin/python -m studyguide.preview                  # all topics
    .venv/bin/python -m studyguide.preview --topic "File Systems" --limit 10
    .venv/bin/python -m studyguide.preview --rejected       # also show what was rejected and why
    .venv/bin/python -m studyguide.preview > preview.txt    # save to a file
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import textwrap

from . import paths
from .flashcards import preview_items
from .generators import SOURCE_CONTEXT


def wrap(text: str, indent: str = "     ") -> str:
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preview generated study questions (read-only).")
    parser.add_argument("--topic", help="only this topic (folder name)")
    parser.add_argument("--limit", type=int, default=0, help="max questions per topic (0 = all)")
    parser.add_argument("--rejected", action="store_true", help="also list rejected candidates")
    args = parser.parse_args(argv)

    path = paths.db_path()
    if not path.exists():
        print("No Study Guide data found yet. Open the app and choose your study folder first.")
        return 1
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM settings WHERE key = 'current_library_id'").fetchone()
    if not row:
        print("No study folder chosen yet. Open the app and choose one first.")
        return 1
    library_id = int(row["value"])

    topics = conn.execute(
        "SELECT id, name FROM topics WHERE library_id = ? AND present = 1 ORDER BY name COLLATE NOCASE",
        (library_id,),
    ).fetchall()
    if args.topic:
        topics = [t for t in topics if t["name"].lower() == args.topic.lower()]
        if not topics:
            print(f"No topic named “{args.topic}”.")
            return 1

    for topic in topics:
        result = preview_items(conn, library_id, topic_id=topic["id"])
        items = result.items[: args.limit] if args.limit else result.items
        print("=" * 100)
        print(f"TOPIC: {topic['name']}  ·  {len(result.items)} questions  ·  "
              f"{len(result.rejected)} candidates rejected  ·  {len(result.skipped_slides)} slides skipped")
        print("=" * 100)
        for n, item in enumerate(items, 1):
            source = ("ADDED CompTIA A+ Core 2 context (not from the slide)" if item.source == SOURCE_CONTEXT
                      else "From the slide")
            print(f"\n{n}. [{item.kind.replace('_', ' ')}] {item.prompt}")
            for o in item.options:
                print(f"     {'✔' if o == item.answer else '•'} {o}")
            print(f"   Answer: {item.answer}")
            print(wrap("Why: " + item.explanation))
            for option, why in item.why_wrong.items():
                print(wrap(f"Not {option}: {why}"))
            print(f"   Source: {source}")
            print(f"   Slide: {item.slide_support!r}")
        if result.skipped_slides:
            print("\n   Slides skipped (not enough information for a good question):")
            for rel in result.skipped_slides:
                print(f"     - {rel}")
        if args.rejected and result.rejected:
            print("\n   Rejected candidates:")
            for r in result.rejected:
                print(f"     ✗ {r.item.prompt}  →  {'; '.join(r.problems)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
