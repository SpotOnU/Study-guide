from conftest import FOOTER, MANGLED_FOOTER

from studyguide import cleanup, flashcards, library, transcripts

DEFAULT = cleanup.Rules()

SLIDE = f"""Ports and protocols
• HTTPS uses port 443 by default
• SSH provides encrypted remote access
• Copyright law protects software from unauthorized copying
Visit example.com for the full port list
{FOOTER}"""


def test_exact_footer_is_removed():
    cleaned, removed = cleanup.clean_text(SLIDE, DEFAULT)
    assert removed == [FOOTER]
    assert "Messer" not in cleaned and "ProfessorMesser" not in cleaned


def test_ocr_mangled_footers_are_removed():
    variants = [
        MANGLED_FOOTER,
        "https //ProfessorMesser.com @ 2025 Messer Studios, LLC",   # lost colon, © read as @
        "https:/ProfessorMesser,com  © 2O25 Messer Studios LLC",     # comma for dot, O for 0
        "httpsl/Professor Messer.corn © 2024 Messer Studlos, LLC",   # rn for m, l for i, other year
        "HTTPS://PROFESSORMESSER.COM © 2025 MESSER STUDIOS, LLC",     # capitalization
        "https://ProfessorMesser.com",                                 # footer split over two lines...
        "© 2025 Messer Studios, LLC",                                  # ...second half
        "e 2025 Messer Studios. LLC",                                  # © read as "e"
    ]
    for footer in variants:
        assert DEFAULT.matches(footer), footer
        assert cleanup.contains_footer(footer), footer


def test_footer_split_across_lines_is_removed():
    text = "Windows editions\n• Home and Pro\nhttps://ProfessorMesser.com\n© 2025 Messer Studios, LLC"
    cleaned, _ = cleanup.clean_text(text, DEFAULT)
    assert cleaned == "Windows editions\n• Home and Pro"


def test_footer_glued_onto_a_content_line_keeps_the_content():
    line = f"• Check the system requirements first {FOOTER}"
    cleaned, removed = cleanup.clean_text(line, DEFAULT)
    assert cleaned == "• Check the system requirements first"
    assert removed == [line]


def test_useful_content_is_not_deleted():
    cleaned, _ = cleanup.clean_text(SLIDE, DEFAULT)
    for kept in ("HTTPS uses port 443 by default",
                 "SSH provides encrypted remote access",
                 "Copyright law protects software from unauthorized copying",  # mentions copyright
                 "Visit example.com for the full port list"):                  # mentions a website
        assert kept in cleaned
    for line in ("Professor Messer Core 2 course notes", "Licensing - copyright and DRM",
                 "Node.js runs JavaScript on servers", "https://example.com/downloads"):
        assert not DEFAULT.matches(line), line


def test_real_copyright_notices_are_removed():
    for notice in ("© 2024 Contoso Ltd.", "Copyright 2023 Fabrikam Inc.", "All rights reserved."):
        assert DEFAULT.matches(notice), notice


def test_custom_phrases_and_builtin_switch():
    rules = cleanup.Rules(builtin=False, phrases=["CompTIA A+ Core 2"])
    assert rules.matches("comptia a+ core-2   (220-1202)")  # ignores case, spacing, punctuation
    assert not rules.matches(FOOTER)  # built-in rules switched off


def test_rules_are_saved(conn):
    cleanup.save_rules(conn, cleanup.Rules(builtin=False, phrases=["A+ Core 1", "Slide"]))
    rules = cleanup.load_rules(conn)
    assert rules.builtin is False and rules.phrases == ["A+ Core 1", "Slide"]


def first_image(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    return lib, library.images_needing_ocr(conn, lib)[0]


def test_new_ocr_readings_are_cleaned_and_raw_reading_kept(conn, study_root):
    _, img = first_image(conn, study_root)
    transcripts.apply_ocr(conn, img["id"], SLIDE.replace(FOOTER, MANGLED_FOOTER), "fake", img["sha256"])
    tr = transcripts.get_transcript(conn, img["id"])
    assert "Messer" not in tr["text"]
    assert MANGLED_FOOTER in tr["ocr_text"]  # the original reading is preserved


def test_cleaning_existing_transcripts_is_previewed_backed_up_and_undoable(conn, study_root):
    _, img = first_image(conn, study_root)
    original = SLIDE + "\nMy own note"
    transcripts.save_transcript(conn, img["id"], original)

    preview = cleanup.preview_all(conn, DEFAULT)
    assert [(i, removed) for i, _, removed in preview] == [(img["id"], [FOOTER])]
    assert transcripts.get_transcript(conn, img["id"])["text"] == original  # preview changes nothing

    assert cleanup.clean_all(conn, DEFAULT) == 1
    text = transcripts.get_transcript(conn, img["id"])["text"]
    assert FOOTER not in text and "My own note" in text and "SSH provides" in text
    assert cleanup.clean_all(conn, DEFAULT) == 0  # nothing left to do

    assert cleanup.undo_last_cleanup(conn) == 1
    assert transcripts.get_transcript(conn, img["id"])["text"] == original


def test_footer_cannot_become_study_content(conn, study_root):
    """Even if a footer is still in a transcript (e.g. the user turned cleanup off),
    the generator ignores it and the validator rejects any item containing it."""
    lib, img = first_image(conn, study_root)
    cleanup.save_rules(conn, cleanup.Rules(builtin=False))
    transcripts.save_transcript(conn, img["id"], SLIDE + "\n" + MANGLED_FOOTER)
    flashcards.sync_cards(conn, lib)
    rows = conn.execute("SELECT front, back, context, explanation, details FROM cards").fetchall()
    assert rows, "the slide should still produce real questions"
    for row in rows:
        for value in row:
            assert "messer" not in value.lower(), value
