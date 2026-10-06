from studyguide import cleanup, flashcards, library, transcripts

FOOTER = "https://ProfessorMesser.com © 2025 Messer Studios, LLC"
SLIDE = f"""Ports and Protocols
• HTTPS uses port 443 by default
• SSH provides encrypted remote access
Visit example.com for the full port list
{FOOTER}"""

DEFAULT = cleanup.Rules()


def test_messer_footer_removed_in_its_usual_forms():
    for footer in (
        FOOTER,
        "© 2025 Messer Studios, LLC",
        "©2025 Messer Studios, LLC",
        "https://ProfessorMesser.com",
        "www.professormesser.com",
        "Copyright 2025 Messer Studios",
        "(c) 2025 Messer Studios. All rights reserved.",
    ):
        assert DEFAULT.matches(footer), footer


def test_real_content_is_kept():
    cleaned, removed = cleanup.clean_text(SLIDE, DEFAULT)
    assert removed == [FOOTER]
    assert "HTTPS uses port 443 by default" in cleaned
    assert "Visit example.com for the full port list" in cleaned  # a sentence, not just a URL
    assert "Node.js" not in [r for r in removed]
    assert not DEFAULT.matches("Node.js runs JavaScript on servers")
    assert not DEFAULT.matches("")


def test_custom_phrases_and_builtin_switch():
    rules = cleanup.Rules(builtin=False, phrases=["messer studios", "Slide"])
    assert rules.matches("© 2025 Messer Studios, LLC")  # via phrase, case-insensitive
    assert rules.matches("Slide 4 of 30")
    assert not rules.matches("https://ProfessorMesser.com")  # built-in rules off


def test_rules_are_saved(conn):
    cleanup.save_rules(conn, cleanup.Rules(builtin=False, phrases=["A+ Core 1", "Slide"]))
    rules = cleanup.load_rules(conn)
    assert rules.builtin is False and rules.phrases == ["A+ Core 1", "Slide"]
    assert cleanup.load_rules(conn).builtin is False


def setup_slide(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    img = library.images_needing_ocr(conn, lib)[0]
    return lib, img


def test_new_ocr_readings_are_cleaned_but_raw_reading_kept(conn, study_root):
    _, img = setup_slide(conn, study_root)
    transcripts.apply_ocr(conn, img["id"], SLIDE, "fake", img["sha256"])
    tr = transcripts.get_transcript(conn, img["id"])
    assert FOOTER not in tr["text"]
    assert FOOTER in tr["ocr_text"]


def test_clean_all_tidies_old_and_edited_transcripts_keeping_other_text(conn, study_root):
    lib, img = setup_slide(conn, study_root)
    transcripts.save_transcript(conn, img["id"], SLIDE + "\nMy own note")
    assert cleanup.count_affected(conn, DEFAULT) == 1
    assert cleanup.clean_all(conn, DEFAULT) == 1
    text = transcripts.get_transcript(conn, img["id"])["text"]
    assert FOOTER not in text and "My own note" in text and "SSH provides" in text
    assert cleanup.clean_all(conn, DEFAULT) == 0  # nothing left to do


def test_footer_cards_are_retired_after_cleanup(conn, study_root):
    lib, img = setup_slide(conn, study_root)
    transcripts.save_transcript(conn, img["id"], SLIDE)  # saved before cleanup existed
    flashcards.sync_cards(conn, lib)
    footer_cards = conn.execute(
        "SELECT id FROM cards WHERE context = ? AND retired = 0", (FOOTER,)
    ).fetchall()
    assert footer_cards  # the footer had become a card

    cleanup.clean_all(conn, DEFAULT)
    flashcards.sync_cards(conn, lib)
    assert not conn.execute(
        "SELECT id FROM cards WHERE context = ? AND retired = 0", (FOOTER,)
    ).fetchall()
