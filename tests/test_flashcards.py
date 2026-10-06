import os
import random
from datetime import datetime, timedelta, timezone

import pytest

from studyguide import flashcards, library, progress, transcripts
from studyguide.db import iso
from studyguide.generators import SlideText
from studyguide.generators.offline import OfflineGenerator
from studyguide.rounds import Round

SLIDE = """Mitochondria
• Site of cellular respiration
• Produce ATP from glucose and oxygen
• Inner membrane folds = cristae
Osmosis: movement of water across a membrane
• Short line"""

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- generator

def test_generator_makes_varied_cards_only_from_slide_words():
    cards = OfflineGenerator().flashcards(SlideText(1, "Biology", "Biology/a.png", SLIDE))
    kinds = [c.kind for c in cards]
    assert "cloze" in kinds and "definition" in kinds and "reverse" in kinds
    for card in cards:
        assert card.back in SLIDE, f"answer {card.back!r} is not on the slide"
        assert card.context in SLIDE.replace("• ", "")
    atp = next(c for c in cards if c.back == "ATP")
    assert "_____" in atp.front and "ATP" not in atp.front
    assert not any("Short line" in c.context for c in cards)


def test_generator_handles_empty_text():
    assert OfflineGenerator().flashcards(SlideText(1, "T", "T/a.png", "")) == []


# ---------------------------------------------------------------- syncing

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


def test_sync_is_idempotent(conn, lib):
    img = image_id(conn, "Biology/slide01.png")
    transcripts.save_transcript(conn, img, SLIDE)
    first = flashcards.sync_cards(conn, lib)
    assert first.added >= 4
    again = flashcards.sync_cards(conn, lib)
    assert (again.added, again.retired) == (0, 0)


def test_editing_transcript_keeps_history_and_retires_only_changed_cards(conn, lib):
    img = image_id(conn, "Biology/slide01.png")
    transcripts.save_transcript(conn, img, SLIDE)
    flashcards.sync_cards(conn, lib)
    atp = next(c for c in active_cards(conn, img) if c["back"] == "ATP")
    flashcards.grade_card(conn, atp["id"], "good", NOW)

    # fix a line that has nothing to do with ATP
    transcripts.save_transcript(conn, img, SLIDE.replace("cellular respiration", "aerobic respiration"))
    result = flashcards.sync_cards(conn, lib)
    assert result.added == 1 and result.retired == 1
    still = flashcards.get_card(conn, atp["id"])
    assert still["retired"] == 0 and still["reps"] == 1

    # undo the edit: the old card comes back rather than a duplicate
    transcripts.save_transcript(conn, img, SLIDE)
    result = flashcards.sync_cards(conn, lib)
    assert result.restored == 1 and result.added == 0


def test_cards_of_missing_slides_are_kept_but_not_studied(conn, lib, study_root):
    img = image_id(conn, "Chemistry/atoms.png")
    transcripts.save_transcript(conn, img, SLIDE)
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
        transcripts.save_transcript(conn, row["id"], SLIDE)
    flashcards.sync_cards(conn, lib)
    r = Round(conn, flashcards.build_round(conn, lib), now=lambda: NOW)
    while r.current is not None:
        r.answer("good")
    r.finish()
    assert snapshot(study_root) == before


# ---------------------------------------------------------------- rounds

@pytest.fixture
def deck(conn, lib):
    for rel in ("Biology/slide01.png", "Biology/slide02.PNG", "Chemistry/atoms.png"):
        transcripts.save_transcript(conn, image_id(conn, rel), SLIDE.replace("Mitochondria", rel))
    flashcards.sync_cards(conn, lib)
    return lib


def test_round_never_pairs_a_definition_with_its_reverse(conn, deck):
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
    # badges are only awarded once
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
