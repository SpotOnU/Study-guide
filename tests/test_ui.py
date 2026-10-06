"""Drive the real window offscreen with a fake OCR engine."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

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
        return (
            "Mitochondria\n• Site of cellular respiration\n• Produce ATP from glucose and oxygen\n"
            f"Osmosis: movement of water across a membrane ({path.stem})"
        )


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
