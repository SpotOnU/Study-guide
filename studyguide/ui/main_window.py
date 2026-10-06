"""Main window: choose a study folder, browse topics and slides, edit transcripts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db, library, transcripts
from ..ocr import OCREngine

IMAGE_ROLE = Qt.UserRole + 1


class OCRWorker(QObject):
    """Runs OCR off the UI thread. It never touches the database."""

    result = Signal(int, str, str)  # image_id, sha256, text
    failed = Signal(int, str)
    progress = Signal(int, int)  # done, total
    finished = Signal()

    def __init__(self, engine: OCREngine, jobs: List[Tuple[int, str, Path]]):
        super().__init__()
        self.engine = engine
        self.jobs = jobs
        self.stop_requested = False

    def run(self) -> None:
        total = len(self.jobs)
        for done, (image_id, sha, path) in enumerate(self.jobs, start=1):
            if self.stop_requested:
                break
            try:
                self.result.emit(image_id, sha, self.engine.recognize(path))
            except Exception as exc:  # keep going on a bad image
                self.failed.emit(image_id, str(exc))
            self.progress.emit(done, total)
        self.finished.emit()


class ImageView(QScrollArea):
    """Shows a slide scaled to the available width."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.label = QLabel("Choose a slide on the left.")
        self.label.setAlignment(Qt.AlignCenter)
        self.setWidget(self.label)
        self._pixmap: Optional[QPixmap] = None

    def show_image(self, path: Optional[Path]) -> None:
        self._pixmap = None
        if path is None:
            self.label.setPixmap(QPixmap())
            self.label.setText("Choose a slide on the left.")
            return
        pixmap = QPixmap(str(path))  # read-only load
        if pixmap.isNull():
            self.label.setPixmap(QPixmap())
            self.label.setText(f"Could not open {path.name}")
            return
        self._pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None:
            return
        width = max(100, self.viewport().width() - 4)
        self.label.setPixmap(
            self._pixmap.scaledToWidth(min(width, self._pixmap.width()), Qt.SmoothTransformation)
        )


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, ocr_engine: Optional[OCREngine]):
        super().__init__()
        self.conn = conn
        self.ocr_engine = ocr_engine
        self.library_id: Optional[int] = None
        self.current_image_id: Optional[int] = None
        self._ocr_thread: Optional[QThread] = None
        self._ocr_worker: Optional[OCRWorker] = None

        self.setWindowTitle("Study Guide")
        self.resize(1300, 820)
        self._build_ui()

        saved = db.get_setting(conn, "current_library_id")
        if saved:
            self.library_id = int(saved)
            self.refresh_library()
        self._update_enabled()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Library")
        toolbar.setMovable(False)
        self.choose_action = QAction("Choose Study Folder…", self)
        self.choose_action.triggered.connect(self.choose_folder)
        self.refresh_action = QAction("Refresh Library", self)
        self.refresh_action.setShortcut(QKeySequence.Refresh)
        self.refresh_action.triggered.connect(self.refresh_library)
        self.ocr_action = QAction("Read Text from New Slides", self)
        self.ocr_action.triggered.connect(self.transcribe_pending)
        for action in (self.choose_action, self.refresh_action, self.ocr_action):
            toolbar.addAction(action)

        self.folder_label = QLabel()
        self.folder_label.setContentsMargins(12, 0, 0, 0)
        toolbar.addWidget(self.folder_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Topics and slides"])
        self.tree.currentItemChanged.connect(self._on_selection_changed)

        self.image_view = ImageView()

        self.source_label = QLabel("No slide selected")
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Transcript of this slide. Fix any mistakes here; your edits are kept."
        )
        self.editor.modificationChanged.connect(lambda _: self._update_enabled())

        self.save_button = QPushButton("Save")
        self.save_button.setShortcut(QKeySequence.Save)
        self.save_button.clicked.connect(self.save_current)
        self.revert_button = QPushButton("Undo Unsaved Changes")
        self.revert_button.clicked.connect(self._load_transcript)
        self.reread_button = QPushButton("Re-read Text from Image")
        self.reread_button.clicked.connect(self.reread_current)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)
        buttons.addWidget(self.reread_button)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.source_label)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.editor, 1)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.image_view)
        splitter.addWidget(right)
        splitter.setSizes([260, 620, 420])
        self.setCentralWidget(splitter)

        if self.ocr_engine is None:
            self.statusBar().showMessage(
                "Automatic text reading is unavailable (needs macOS). "
                "You can still type transcripts by hand."
            )

    def _update_enabled(self) -> None:
        has_library = self.library_id is not None
        has_image = self.current_image_id is not None
        busy = self._ocr_thread is not None
        self.refresh_action.setEnabled(has_library and not busy)
        self.ocr_action.setEnabled(has_library and self.ocr_engine is not None and not busy)
        self.choose_action.setEnabled(not busy)
        self.editor.setEnabled(has_image)
        modified = has_image and self.editor.document().isModified()
        self.save_button.setEnabled(modified)
        self.revert_button.setEnabled(modified)
        self.reread_button.setEnabled(has_image and self.ocr_engine is not None and not busy)

    # ------------------------------------------------------------- library
    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose your main study folder")
        if folder:
            self.open_folder(Path(folder))

    def open_folder(self, folder: Path) -> None:
        self._autosave()
        self.library_id = library.get_or_create_library(self.conn, folder)
        db.set_setting(self.conn, "current_library_id", str(self.library_id))
        self.current_image_id = None
        self.refresh_library()

    def refresh_library(self) -> None:
        if self.library_id is None:
            return
        self._autosave()
        root = library.library_root(self.conn, self.library_id)
        self.folder_label.setText(str(root))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = library.scan_library(self.conn, self.library_id)
        except FileNotFoundError as exc:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage(str(exc))
            QMessageBox.warning(
                self,
                "Study folder not found",
                f"{exc}\n\nIf it moved, use “Choose Study Folder…” to pick it again. "
                "Your transcripts are still saved.",
            )
            self._populate_tree()
            return
        QApplication.restoreOverrideCursor()
        self._populate_tree()
        self.statusBar().showMessage(result.summary())
        self._update_enabled()

    def _populate_tree(self) -> None:
        selected = self.current_image_id
        self.tree.blockSignals(True)
        self.tree.clear()
        select_item = None
        for topic in library.list_topics(self.conn, self.library_id):
            count = topic["image_count"] or 0
            done = topic["transcribed_count"] or 0
            topic_item = QTreeWidgetItem([f"{topic['name']}  ({done}/{count} transcribed)"])
            topic_item.setFlags(topic_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(topic_item)
            for img in library.list_images(self.conn, topic["id"]):
                name = img["rel_path"].split("/", 1)[1]
                if img["transcript"]:
                    stale = img["ocr_sha256"] and img["ocr_sha256"] != img["sha256"]
                    marker = "⚠" if stale else ("✎" if img["edited"] else "✓")
                else:
                    marker = "○"
                item = QTreeWidgetItem([f"{marker}  {name}"])
                item.setData(0, IMAGE_ROLE, img["id"])
                item.setToolTip(0, img["rel_path"])
                topic_item.addChild(item)
                if img["id"] == selected:
                    select_item = item
            topic_item.setExpanded(True)
        self.tree.blockSignals(False)
        if select_item is not None:
            self.tree.setCurrentItem(select_item)
        else:
            self.current_image_id = None
            self._show_current()

    # --------------------------------------------------------- transcripts
    def _on_selection_changed(self, current, _previous) -> None:
        image_id = current.data(0, IMAGE_ROLE) if current is not None else None
        if image_id == self.current_image_id:
            return
        self._autosave()
        self.current_image_id = image_id
        self._show_current()

    def _show_current(self) -> None:
        if self.current_image_id is None:
            self.image_view.show_image(None)
            self.source_label.setText("No slide selected")
            self.status_label.clear()
            self.editor.clear()
            self.editor.document().setModified(False)
            self._update_enabled()
            return
        row = library.get_image(self.conn, self.current_image_id)
        path = Path(row["root_path"]) / row["rel_path"]
        self.image_view.show_image(path)
        self.source_label.setText(f"<b>Topic:</b> {row['topic_name']}<br><b>Slide:</b> {row['rel_path']}")
        self._load_transcript()

    def _load_transcript(self) -> None:
        if self.current_image_id is None:
            return
        tr = transcripts.get_transcript(self.conn, self.current_image_id)
        row = library.get_image(self.conn, self.current_image_id)
        self.editor.setPlainText(tr["text"] if tr else "")
        self.editor.document().setModified(False)
        if tr is None:
            status = "Not transcribed yet."
        elif tr["ocr_sha256"] and tr["ocr_sha256"] != row["sha256"]:
            status = "⚠ The image file changed since its text was read. Consider re-reading it."
        elif tr["edited"]:
            status = f"✎ Edited by you · last saved {tr['updated_at']}"
        else:
            status = f"✓ Read automatically ({tr['ocr_engine']}). Please check for mistakes."
        self.status_label.setText(status)
        self._update_enabled()

    def save_current(self) -> None:
        if self.current_image_id is None:
            return
        transcripts.save_transcript(self.conn, self.current_image_id, self.editor.toPlainText())
        self._load_transcript()
        self._populate_tree()
        self.statusBar().showMessage("Transcript saved.", 3000)

    def _autosave(self) -> None:
        if self.current_image_id is not None and self.editor.document().isModified():
            transcripts.save_transcript(
                self.conn, self.current_image_id, self.editor.toPlainText()
            )
            self.editor.document().setModified(False)

    # ----------------------------------------------------------------- OCR
    def transcribe_pending(self) -> None:
        if self.library_id is None or self.ocr_engine is None:
            return
        self._autosave()
        root = library.library_root(self.conn, self.library_id)
        jobs = [
            (r["id"], r["sha256"], root / r["rel_path"])
            for r in library.images_needing_ocr(self.conn, self.library_id)
        ]
        if not jobs:
            self.statusBar().showMessage("All slides already have text. Nothing new to read.")
            return
        self._start_ocr(jobs, replace_edits=False)

    def reread_current(self) -> None:
        if self.current_image_id is None or self.ocr_engine is None:
            return
        tr = transcripts.get_transcript(self.conn, self.current_image_id)
        if (tr and tr["edited"]) or self.editor.document().isModified():
            answer = QMessageBox.question(
                self,
                "Replace your edits?",
                "You have edited this transcript. Replace your text with a fresh reading "
                "of the image?\n\nChoose No to keep your text.",
            )
            if answer != QMessageBox.Yes:
                return
        self.editor.document().setModified(False)
        row = library.get_image(self.conn, self.current_image_id)
        path = Path(row["root_path"]) / row["rel_path"]
        self._start_ocr([(row["id"], row["sha256"], path)], replace_edits=True)

    def _start_ocr(self, jobs, replace_edits: bool) -> None:
        self._replace_edits = replace_edits
        self._ocr_failures: List[str] = []
        self._ocr_thread = QThread(self)
        self._ocr_worker = OCRWorker(self.ocr_engine, jobs)
        self._ocr_worker.moveToThread(self._ocr_thread)
        self._ocr_thread.started.connect(self._ocr_worker.run)
        self._ocr_worker.result.connect(self._on_ocr_result)
        self._ocr_worker.failed.connect(self._on_ocr_failed)
        self._ocr_worker.progress.connect(
            lambda done, total: self.statusBar().showMessage(f"Reading slides… {done}/{total}")
        )
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._update_enabled()
        self._ocr_thread.start()

    def _on_ocr_result(self, image_id: int, sha: str, text: str) -> None:
        transcripts.apply_ocr(
            self.conn, image_id, text, self.ocr_engine.name, sha, replace_edits=self._replace_edits
        )
        if image_id == self.current_image_id and not self.editor.document().isModified():
            self._load_transcript()

    def _on_ocr_failed(self, image_id: int, message: str) -> None:
        self._ocr_failures.append(message)

    def _on_ocr_finished(self) -> None:
        self._ocr_thread.quit()
        self._ocr_thread.wait()
        self._ocr_thread = None
        self._ocr_worker = None
        self._populate_tree()
        if self._ocr_failures:
            self.statusBar().showMessage(f"Done, but {len(self._ocr_failures)} slide(s) could not be read.")
            QMessageBox.warning(self, "Some slides could not be read", "\n".join(self._ocr_failures[:10]))
        else:
            self.statusBar().showMessage("Finished reading slides. Check the transcripts for mistakes.")
        self._update_enabled()

    # ---------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802
        self._autosave()
        if self._ocr_thread is not None:
            self._ocr_worker.stop_requested = True
            self._ocr_thread.quit()
            self._ocr_thread.wait()
        super().closeEvent(event)
