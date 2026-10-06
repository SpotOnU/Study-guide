import os
import random
from datetime import datetime, timedelta, timezone

import pytest

from studyguide import flashcards, library, progress, transcripts
from studyguide.db import iso
from conftest import APP_SLIDE, FS_SLIDE, MALWARE_SLIDE
from studyguide.rounds import Round

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)

BACKUP_SLIDE = """Backup types
• Full backup: copies all selected data every time
• Incremental backup: copies data changed since the last backup of any type
• Differential backup: copies everything changed since the last full backup
• Test restores regularly"""


@pytest.fixture
def lib(conn, study_root):
    lib_id = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib_id)
    return lib_id


def image_id(conn, rel_path):
    return conn.execute("SELECT id FROM images WHERE rel_path = ?", (rel_path,)).fetchone()["id"]


def active_cards(conn, img):
    return conn.execute(
        "SELECT * FROM cards WHERE image_id = ? AND retired = 0 ORDER BY position", (img,)
    ).fetchall()


# ---------------------------------------------------------------- syncing

def test_sync_stores_explained_items_and_is_idempotent(conn, lib):
    img = image_id(conn, "Biology/slide01.png")
    transcripts.save_transcript(conn, img, MALWARE_SLIDE)
    first = flashcards.sync_cards(conn, lib)
    assert first.added >= 4
    for card in active_cards(conn, img):
        assert card["explanation"] and card["gen_version"] == flashcards.CURRENT_VERSION
        details = flashcards.card_details(card)
        assert details["source"] in ("slide", "context") and details["concept"]
    again = flashcards.sync_cards(conn, lib)
    assert (again.added, again.retired) == (0, 0)


def test_editing_transcript_keeps_history_and_retires_only_changed_cards(conn, lib):
    img = image_id(conn, "Biology/slide01.png")
    transcripts.save_transcript(conn, img, MALWARE_SLIDE)
    flashcards.sync_cards(conn, lib)
    worm = next(c for c in active_cards(conn, img) if c["back"] == "Worm")
    flashcards.grade_card(conn, worm["id"], "good", NOW)

    # remove the Trojan line: only Trojan cards are retired, the Worm card keeps its history
    edited = MALWARE_SLIDE.replace("• Trojan horse: software that pretends to be something else\n", "")
    transcripts.save_transcript(conn, img, edited)
    total_before = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    result = flashcards.sync_cards(conn, lib)
    assert result.retired >= 1
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] >= total_before  # nothing deleted
    still = flashcards.get_card(conn, worm["id"])
    assert still["retired"] == 0 and still["reps"] == 1
    assert all("Trojan" not in c["back"] for c in active_cards(conn, img))

    # undo the edit: the old cards come back rather than duplicates
    transcripts.save_transcript(conn, img, MALWARE_SLIDE)
    result = flashcards.sync_cards(conn, lib)
    assert result.restored >= 1 and result.added == 0


def test_cards_of_missing_slides_are_kept_but_not_studied(conn, lib, study_root):
    img = image_id(conn, "Chemistry/atoms.png")
    transcripts.save_transcript(conn, img, MALWARE_SLIDE)
    flashcards.sync_cards(conn, lib)
    card_ids = [c["id"] for c in active_cards(conn, img)]
    flashcards.grade_card(conn, card_ids[0], "good", NOW)

    os.rename(study_root / "Chemistry" / "atoms.png", study_root / "atoms.bak")
    library.scan_library(conn, lib)
    flashcards.sync_cards(conn, lib)
    assert flashcards.build_round(conn, lib, now=NOW + timedelta(days=30)) == []
    assert flashcards.get_card(conn, card_ids[0])["reps"] == 1

    os.rename(study_root / "atoms.bak", study_root / "Chemistry" / "atoms.png")
    library.scan_library(conn, lib)
    flashcards.sync_cards(conn, lib)
    assert card_ids[0] in flashcards.build_round(conn, lib, now=NOW + timedelta(days=30), size=50)
    assert flashcards.get_card(conn, card_ids[0])["reps"] == 1


def test_study_folder_untouched_by_flashcards(conn, lib, study_root):
    from conftest import snapshot
    before = snapshot(study_root)
    for row in library.images_needing_ocr(conn, lib):
        transcripts.save_transcript(conn, row["id"], MALWARE_SLIDE)
    flashcards.sync_cards(conn, lib)
    r = Round(conn, flashcards.build_round(conn, lib), now=lambda: NOW)
    while r.current is not None:
        r.answer("good")
    r.finish()
    assert snapshot(study_root) == before


# ---------------------------------------------------------------- old fragment cards

def add_old_card(conn, img, front, back, context):
    """Insert a card the way the old (version 1) generator stored it."""
    cur = conn.execute(
        "INSERT INTO cards (image_id, kind, front, back, context, fingerprint, generator, created_at) "
        "VALUES (?, 'cloze', ?, ?, ?, ?, 'offline-basic', '2026-01-01T00:00:00+00:00')",
        (img, front, back, context, f"old-{front}"),
    )
    conn.commit()
    return cur.lastrowid


def test_old_fragment_cards_are_paused_and_offered_for_regeneration(conn, lib):
    img = image_id(conn, "Biology/slide01.png")
    transcripts.save_transcript(conn, img, APP_SLIDE)
    bad = add_old_card(conn, img, "Installing applications\n\nFill in the blank:\nFind the _____ you need",
                       "application", "Find the application you need")
    flashcards.grade_card(conn, bad, "good", NOW)  # it has review history

    result = flashcards.sync_cards(conn, lib)
    assert result.paused == 1 and result.waiting == 1
    card = flashcards.get_card(conn, bad)
    assert card["paused"] and ("instruction" in card["paused"] or "fragment" in card["paused"])
    assert bad not in flashcards.build_round(conn, lib, size=50, now=NOW + timedelta(days=30))
    # the slide is NOT silently regenerated while the old card is waiting for approval
    assert [c["id"] for c in active_cards(conn, img)] == [bad]

    status = flashcards.old_cards_status(conn, lib)
    assert (status.total, status.paused, status.fragments) == (1, 1, 1)
    assert status.examples[0]["back"] == "application"

    preview = flashcards.preview_items(conn, lib, only_waiting=True)
    assert any(i.answer == "Application software" for i in preview.items)
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1  # preview saved nothing

    regen = flashcards.regenerate_old_cards(conn, lib)
    assert regen.added >= 1 and regen.retired >= 1
    new_cards = active_cards(conn, img)
    assert new_cards and all(c["gen_version"] == flashcards.CURRENT_VERSION for c in new_cards)
    assert any(c["back"] == "Application software" for c in new_cards)
    old = flashcards.get_card(conn, bad)
    assert old["retired"] == 1 and old["reps"] == 1  # retired, not deleted; history kept
    assert flashcards.old_cards_status(conn, lib).total == 0


def test_new_slides_get_new_questions_while_old_ones_wait(conn, lib):
    old_img = image_id(conn, "Biology/slide01.png")
    new_img = image_id(conn, "Chemistry/atoms.png")
    transcripts.save_transcript(conn, old_img, APP_SLIDE)
    transcripts.save_transcript(conn, new_img, MALWARE_SLIDE)
    add_old_card(conn, old_img, "Fill in the blank:\nFind the _____ you need", "application", "x")
    flashcards.sync_cards(conn, lib)
    assert active_cards(conn, new_img)
    assert len(active_cards(conn, old_img)) == 1


# ---------------------------------------------------------------- rounds

@pytest.fixture
def deck(conn, lib):
    for rel, text in (("Biology/slide01.png", MALWARE_SLIDE), ("Biology/slide02.PNG", FS_SLIDE),
                      ("Chemistry/atoms.png", APP_SLIDE), ("Biology/Week 2/cells.png", BACKUP_SLIDE)):
        transcripts.save_transcript(conn, image_id(conn, rel), text)
    flashcards.sync_cards(conn, lib)
    return lib


def test_round_never_shows_two_cards_from_the_same_slide_line(conn, deck):
    ids = flashcards.build_round(conn, deck, size=50, now=NOW)
    seen = set()
    for cid in ids:
        card = flashcards.get_card(conn, cid)
        key = (card["image_id"], card["context"])
        assert key not in seen
        seen.add(key)


def test_round_prefers_due_cards_and_limits_new_ones(conn, deck):
    first = flashcards.build_round(conn, deck, size=10, new_limit=5, now=NOW)
    assert len(first) == 10  # nothing due yet, so a full round of new cards
    for cid in first[:3]:
        flashcards.grade_card(conn, cid, "good", NOW)
    later = NOW + timedelta(days=2)
    ids = flashcards.build_round(conn, deck, size=10, new_limit=5, now=later)
    assert set(first[:3]) <= set(ids)
    new_in_round = [i for i in ids if flashcards.get_card(conn, i)["reps"] is None]
    assert len(new_in_round) <= 5


def test_round_for_one_topic(conn, deck):
    chem = conn.execute("SELECT id FROM topics WHERE name = 'Chemistry'").fetchone()["id"]
    ids = flashcards.build_round(conn, deck, topic_id=chem, size=50, now=NOW)
    assert ids and all(flashcards.get_card(conn, i)["topic_name"] == "Chemistry" for i in ids)


def test_missed_card_comes_back_once_and_points_are_encouraging(conn, deck):
    ids = flashcards.build_round(conn, deck, size=5, now=NOW)
    r = Round(conn, ids, now=lambda: NOW, rng=random.Random(1))
    fb = r.answer("again")
    assert not fb.correct and fb.retry_later and fb.xp == progress.XP_TRY
    while r.current is not None:
        fb = r.answer("good")
    assert r.length == 6  # the missed card was shown again at the end
    assert fb.correct and "learned" in fb.message
    summary = r.finish()
    assert summary.total == 5 and summary.correct == 4 and not summary.perfect
    assert summary.missed == [ids[0]]
    assert summary.xp == progress.XP_TRY + 5 * progress.XP_CORRECT + progress.XP_ROUND_DONE
    assert progress.total_xp(conn) == summary.xp
    assert {"first_round", "comeback"} <= set(summary.new_badges)


def test_perfect_round_bonus_and_badge(conn, deck):
    r = Round(conn, flashcards.build_round(conn, deck, size=5, now=NOW), now=lambda: NOW)
    while r.current is not None:
        r.answer("easy")
    s = r.finish()
    assert s.perfect and s.bonus == progress.XP_ROUND_DONE + progress.XP_PERFECT_BONUS
    assert "perfect_round" in s.new_badges
    r2 = Round(conn, flashcards.build_round(conn, deck, size=5, now=NOW), now=lambda: NOW)
    while r2.current is not None:
        r2.answer("good")
    assert "perfect_round" not in r2.finish().new_badges


# ---------------------------------------------------------------- scheduling

def test_schedule_intervals_grow():
    s = flashcards.schedule(None, "good", NOW)
    assert s["interval_days"] == 1.0 and s["due_at"] == iso(NOW + timedelta(days=1))
    s = flashcards.schedule(s, "good", NOW)
    assert s["interval_days"] == 3.0
    s = flashcards.schedule(s, "good", NOW)
    assert s["interval_days"] == 7.5
    s = flashcards.schedule(s, "again", NOW)
    assert s["interval_days"] == 0 and s["lapses"] == 1 and s["reps"] == 0
    assert s["due_at"] == iso(NOW + timedelta(minutes=10))
    assert flashcards.schedule(None, "easy", NOW)["interval_days"] == 3.0
    with pytest.raises(ValueError):
        flashcards.schedule(None, "maybe", NOW)


# ---------------------------------------------------------------- progress

def test_levels():
    assert progress.level_for(0).level == 1
    assert progress.level_for(49).level == 1
    lvl = progress.level_for(60)
    assert (lvl.level, lvl.into_level, lvl.needed) == (2, 10, 150)


def test_streaks(conn, deck):
    card = flashcards.build_round(conn, deck, size=1, now=NOW)[0]
    today = datetime.now().astimezone().replace(hour=12)
    for days_ago in (0, 1, 2, 5, 6, 7, 8):
        flashcards.grade_card(conn, card, "good", today - timedelta(days=days_ago))
    assert progress.streaks(conn, today.date()) == (3, 4)
    # tomorrow, before studying, the streak is still alive
    assert progress.streaks(conn, today.date() + timedelta(days=1))[0] == 3
    assert progress.streaks(conn, today.date() + timedelta(days=2))[0] == 0
