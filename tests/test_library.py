import os

from studyguide import db, library, transcripts
from conftest import make_png, snapshot


def image_ids(conn, library_id):
    return {
        r["rel_path"]: r["id"]
        for r in conn.execute("SELECT id, rel_path FROM images WHERE library_id = ?", (library_id,))
    }


def test_scan_finds_topics_and_pngs(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    result = library.scan_library(conn, lib)

    assert sorted(result.added) == [
        "Biology/Week 2/cells.png",
        "Biology/slide01.png",
        "Biology/slide02.PNG",
        "Chemistry/atoms.png",
    ]
    assert result.loose_root_images == 1
    topics = {t["name"]: t["image_count"] or 0 for t in library.list_topics(conn, lib)}
    assert topics == {"Biology": 3, "Chemistry": 1, "Empty Topic": 0}


def test_rescan_adds_new_images_and_keeps_existing_ids_and_transcripts(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    before = image_ids(conn, lib)
    slide = before["Biology/slide01.png"]
    transcripts.save_transcript(conn, slide, "Mitochondria make ATP (my fix)")

    make_png(study_root / "Biology" / "slide03.png", 80)
    make_png(study_root / "Physics" / "forces.png", 90)
    result = library.scan_library(conn, lib)

    assert sorted(result.added) == ["Biology/slide03.png", "Physics/forces.png"]
    assert result.topics_added == ["Physics"]
    assert result.unchanged == 4
    after = image_ids(conn, lib)
    for rel_path, image_id in before.items():
        assert after[rel_path] == image_id
    assert transcripts.get_transcript(conn, slide)["text"] == "Mitochondria make ATP (my fix)"


def test_rescan_twice_is_stable(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    result = library.scan_library(conn, lib)
    assert (result.added, result.changed, result.missing, result.restored) == ([], [], [], [])
    assert result.unchanged == 4


def test_missing_image_keeps_transcript_and_is_restored(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    image_id = image_ids(conn, lib)["Chemistry/atoms.png"]
    transcripts.save_transcript(conn, image_id, "Protons, neutrons, electrons")

    moved = study_root.parent / "atoms-backup.png"
    os.rename(study_root / "Chemistry" / "atoms.png", moved)  # simulate the user moving it away
    result = library.scan_library(conn, lib)
    assert result.missing == ["Chemistry/atoms.png"]
    assert [r["id"] for r in library.list_images(conn, library.get_image(conn, image_id)["topic_id"])] == []
    assert transcripts.get_transcript(conn, image_id)["text"] == "Protons, neutrons, electrons"

    os.rename(moved, study_root / "Chemistry" / "atoms.png")
    result = library.scan_library(conn, lib)
    assert result.restored == ["Chemistry/atoms.png"]
    assert image_ids(conn, lib)["Chemistry/atoms.png"] == image_id
    assert transcripts.get_transcript(conn, image_id)["text"] == "Protons, neutrons, electrons"


def test_removed_topic_hidden_then_restored(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    os.rename(study_root / "Chemistry", study_root.parent / "Chem-away")
    library.scan_library(conn, lib)
    assert "Chemistry" not in [t["name"] for t in library.list_topics(conn, lib)]
    os.rename(study_root.parent / "Chem-away", study_root / "Chemistry")
    library.scan_library(conn, lib)
    assert "Chemistry" in [t["name"] for t in library.list_topics(conn, lib)]


def test_changed_image_is_flagged_for_rereading_but_transcript_kept(conn, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    image_id = image_ids(conn, lib)["Biology/slide01.png"]
    sha = library.get_image(conn, image_id)["sha256"]
    transcripts.apply_ocr(conn, image_id, "old text", "fake", sha)
    assert image_id not in [r["id"] for r in library.images_needing_ocr(conn, lib)]

    make_png(study_root / "Biology" / "slide01.png", 99, size=8)  # user replaced the screenshot
    result = library.scan_library(conn, lib)
    assert result.changed == ["Biology/slide01.png"]
    assert transcripts.get_transcript(conn, image_id)["text"] == "old text"
    assert image_id in [r["id"] for r in library.images_needing_ocr(conn, lib)]


def test_data_survives_reopening_the_database(tmp_path, study_root):
    path = tmp_path / "persist.sqlite3"
    conn = db.connect(path)
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    image_id = image_ids(conn, lib)["Biology/slide02.PNG"]
    transcripts.save_transcript(conn, image_id, "kept")
    db.set_setting(conn, "current_library_id", str(lib))
    conn.close()

    conn = db.connect(path)
    assert db.get_setting(conn, "current_library_id") == str(lib)
    assert library.get_or_create_library(conn, study_root) == lib
    library.scan_library(conn, lib)
    assert transcripts.get_transcript(conn, image_id)["text"] == "kept"
    conn.close()


def test_study_folder_is_never_modified(conn, study_root):
    before = snapshot(study_root)
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    for row in library.images_needing_ocr(conn, lib):
        transcripts.apply_ocr(conn, row["id"], "text", "fake", row["sha256"])
        transcripts.save_transcript(conn, row["id"], "edited")
    library.scan_library(conn, lib)
    assert snapshot(study_root) == before


def test_missing_study_folder_raises_without_losing_data(conn, tmp_path, study_root):
    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    os.rename(study_root, tmp_path / "elsewhere")
    try:
        library.scan_library(conn, lib)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")
    assert len(image_ids(conn, lib)) == 4
