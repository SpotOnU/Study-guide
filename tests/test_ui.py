"""Drive the real window offscreen with a fake OCR engine."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QtCore = pytest.importorskip("PySide6.QtCore")

from studyguide import library, transcripts  # noqa: E402
from studyguide.ocr import OCREngine  # noqa: E402
from studyguide.ui.main_window import IMAGE_ROLE, MainWindow  # noqa: E402
from conftest import snapshot  # noqa: E402


class FakeOCR(OCREngine):
    name = "fake"

    def recognize(self, path):
        return f"text of {path.name}"


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def image_items(window):
    tree = window.tree
    for i in range(tree.topLevelItemCount()):
        topic = tree.topLevelItem(i)
        for j in range(topic.childCount()):
            yield topic.child(j)


def wait_for_ocr(qapp, window, timeout=10):
    end = time.time() + timeout
    while window._ocr_thread is not None and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert window._ocr_thread is None, "OCR did not finish"


def test_full_flow(qapp, conn, study_root):
    before = snapshot(study_root)
    window = MainWindow(conn, FakeOCR())
    window.open_folder(study_root)

    items = list(image_items(window))
    assert len(items) == 4

    # Read text from all slides
    window.transcribe_pending()
    wait_for_ocr(qapp, window)
    lib = window.library_id
    assert library.images_needing_ocr(conn, lib) == []

    # Select a slide, check its transcript and source label
    item = next(image_items(window))
    window.tree.setCurrentItem(item)
    image_id = item.data(0, IMAGE_ROLE)
    assert window.current_image_id == image_id
    assert window.editor.toPlainText().startswith("text of ")
    assert window.topic_chip.text() == "Biology"
    assert window.source_label.text() == item.toolTip(0).split("/", 1)[1]
    assert window.image_view._pixmap is not None

    # Edit, then switch slides: the edit is saved automatically
    window.editor.selectAll()
    window.editor.insertPlainText("corrected text")  # like typing
    assert window.save_button.isEnabled()
    window.tree.setCurrentItem(list(image_items(window))[1])
    assert transcripts.get_transcript(conn, image_id)["text"] == "corrected text"

    # Reading again does not overwrite the edit
    window.transcribe_pending()  # nothing pending
    assert transcripts.get_transcript(conn, image_id)["text"] == "corrected text"

    # Refresh keeps everything
    window.refresh_library()
    assert transcripts.get_transcript(conn, image_id)["text"] == "corrected text"

    window.close()
    assert snapshot(study_root) == before


def test_remembers_last_folder(qapp, conn, study_root):
    first = MainWindow(conn, None)
    assert first.pages.currentIndex() == 0  # welcome screen
    first.open_folder(study_root)
    assert first.pages.currentIndex() == 1
    first.close()
    second = MainWindow(conn, None)
    assert second.library_id == first.library_id
    assert len(list(image_items(second))) == 4
    assert not second.ocr_button.isEnabled()  # no OCR engine available
    second.close()


class SlideOCR(OCREngine):
    name = "fake"

    def recognize(self, path):
        from conftest import MALWARE_SLIDE
        return MALWARE_SLIDE


def test_flashcard_round_in_the_window(qapp, conn, study_root):
    from studyguide import progress

    before = snapshot(study_root)
    window = MainWindow(conn, SlideOCR())
    window.open_folder(study_root)
    window.transcribe_pending()
    wait_for_ocr(qapp, window)

    window.show_view("flashcards")
    page = window.flashcards_page
    assert window.pages.currentWidget() is page
    assert not window.refresh_button.isVisibleTo(window)  # library-only button hidden

    page.start_round(None)
    assert page.in_round()
    length = page.round.length
    page.reveal()
    assert page.answer_box.isVisibleTo(page)
    assert page.card_explanation.text()  # every card explains its answer
    assert page.card_context.text()      # and shows where it came from
    page.grade("again")  # missed: comes back at the end
    assert page.round.length == length + 1
    page.next_card()
    page.reveal()
    page.hide_current()  # hiding works mid-round
    while page.in_round() and page.round.current is not None:
        page.reveal()
        page.grade("good")
        page.next_card()
    assert not page.in_round()
    assert page.stack.currentIndex() == 2  # summary
    assert progress.total_xp(conn) > 0
    assert "first_round" in progress.earned_badges(conn)
    assert window.xp_stat.text().startswith("⭐ Level")

    page.show_home()
    assert page.stack.currentIndex() == 0
    window.show_view("library")
    assert window.pages.currentIndex() == 1
    window.close()
    assert snapshot(study_root) == before


def test_existing_transcripts_cleaned_once_on_upgrade(qapp, conn, study_root):
    from studyguide import db

    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    img = library.images_needing_ocr(conn, lib)[0]
    footer = "https //ProfessorMesser,com @ 2O25 Messer Studlos LLC"  # OCR-mangled
    transcripts.save_transcript(conn, img["id"], "Real content line\n" + footer)
    window = MainWindow(conn, None)
    assert transcripts.get_transcript(conn, img["id"])["text"] == "Real content line"
    assert db.get_setting(conn, "cleanup_v2_applied") == "1"
    assert "footer" in window.statusBar().currentMessage()
    window.close()
    # it runs only once...
    transcripts.save_transcript(conn, img["id"], "Real content line\n" + footer)
    MainWindow(conn, None).close()
    assert footer in transcripts.get_transcript(conn, img["id"])["text"]


def test_ignore_text_dialog(qapp, conn, study_root):
    from studyguide import cleanup
    from studyguide.ui.ignore_dialog import IgnoreTextDialog

    lib = library.get_or_create_library(conn, study_root)
    library.scan_library(conn, lib)
    img = library.images_needing_ocr(conn, lib)[0]
    transcripts.save_transcript(conn, img["id"], "Keep me\nCompTIA A+ Core 1 - Domain 2")
    dialog = IgnoreTextDialog(conn)
    dialog.phrases.setPlainText("CompTIA A+ Core 1")
    assert "1 transcript" in dialog.preview.text()
    dialog.save()
    assert dialog.changed_count == 1
    assert transcripts.get_transcript(conn, img["id"])["text"] == "Keep me"
    assert cleanup.load_rules(conn).phrases == ["CompTIA A+ Core 1"]


def test_old_cards_are_paused_and_upgrade_is_offered(qapp, conn, study_root):
    from conftest import APP_SLIDE
    from studyguide import flashcards
    from studyguide.ui.upgrade_dialog import UpgradeDialog

    window = MainWindow(conn, None)
    window.open_folder(study_root)
    lib = window.library_id
    img = library.images_needing_ocr(conn, lib)[0]
    transcripts.save_transcript(conn, img["id"], APP_SLIDE)
    conn.execute(
        "INSERT INTO cards (image_id, kind, front, back, context, fingerprint, generator, created_at) "
        "VALUES (?, 'cloze', 'Fill in the blank:\nFind the _____ you need', 'application', "
        "'Find the application you need', 'old', 'offline-basic', '2026-01-01')", (img["id"],))
    conn.commit()

    window.show_view("flashcards")
    page = window.flashcards_page
    banners = page.findChildren(QtWidgets.QFrame, "UpgradeBanner")
    assert banners, "the home screen offers to regenerate old cards"

    dialog = UpgradeDialog(conn, lib)
    texts = " ".join(lbl.text() for lbl in dialog.findChildren(QtWidgets.QLabel))
    assert "Find the _____ you need" in texts          # shows the paused card and why
    assert "Which type of software lets a user perform a specific task" in texts  # and the new question
    dialog.regenerate()
    assert flashcards.old_cards_status(conn, lib).total == 0
    page.show_home()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)  # flush old widgets
    assert not page.findChildren(QtWidgets.QFrame, "UpgradeBanner")
    window.close()
