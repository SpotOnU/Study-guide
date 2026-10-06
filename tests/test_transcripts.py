from studyguide import library, transcripts


def first_image(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    return library.images_needing_ocr(conn, lib)[0]


def test_ocr_fills_new_transcript(conn, study_root):
    img = first_image(conn, study_root)
    assert transcripts.apply_ocr(conn, img["id"], "Read text", "fake", img["sha256"]) is True
    tr = transcripts.get_transcript(conn, img["id"])
    assert (tr["text"], tr["ocr_text"], tr["edited"]) == ("Read text", "Read text", 0)


def test_manual_edits_survive_reocr(conn, study_root):
    img = first_image(conn, study_root)
    transcripts.apply_ocr(conn, img["id"], "Mitocondria", "fake", img["sha256"])
    transcripts.save_transcript(conn, img["id"], "Mitochondria")

    replaced = transcripts.apply_ocr(conn, img["id"], "Mitocondria v2", "fake", img["sha256"])
    tr = transcripts.get_transcript(conn, img["id"])
    assert replaced is False
    assert tr["text"] == "Mitochondria"
    assert tr["ocr_text"] == "Mitocondria v2"
    assert tr["edited"] == 1


def test_replace_edits_when_explicitly_asked(conn, study_root):
    img = first_image(conn, study_root)
    transcripts.save_transcript(conn, img["id"], "my text")
    assert transcripts.apply_ocr(conn, img["id"], "fresh", "fake", img["sha256"], replace_edits=True)
    tr = transcripts.get_transcript(conn, img["id"])
    assert (tr["text"], tr["edited"]) == ("fresh", 0)


def test_unedited_ocr_text_is_updated_by_reocr(conn, study_root):
    img = first_image(conn, study_root)
    transcripts.apply_ocr(conn, img["id"], "first", "fake", img["sha256"])
    assert transcripts.apply_ocr(conn, img["id"], "second", "fake", img["sha256"]) is True
    assert transcripts.get_transcript(conn, img["id"])["text"] == "second"
