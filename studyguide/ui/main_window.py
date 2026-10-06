"""Main window: choose a study folder, browse topics and slides, edit transcripts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db, library, transcripts
from .. import cleanup, progress
from ..ocr import OCREngine
from . import theme
from .flashcards_page import FlashcardsPage
from .ignore_dialog import IgnoreTextDialog
from .widgets import button, card

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

    PLACEHOLDER = "👈  Pick a slide to start"

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.label = QLabel(self.PLACEHOLDER)
        self.label.setObjectName("Placeholder")
        self.label.setAlignment(Qt.AlignCenter)
        self.setWidget(self.label)
        self._pixmap: Optional[QPixmap] = None

    def show_image(self, path: Optional[Path]) -> None:
        self._pixmap = None
        self.label.setPixmap(QPixmap())
        if path is None:
            self.label.setText(self.PLACEHOLDER)
            return
        pixmap = QPixmap(str(path))  # read-only load
        if pixmap.isNull():
            self.label.setText(f"😕  Couldn't open {path.name}")
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
        self.view = "library"
        self._topic_colors: dict = {}
        self._ocr_thread: Optional[QThread] = None
        self._ocr_worker: Optional[OCRWorker] = None

        self.setWindowTitle("Study Guide")
        self.resize(1320, 840)
        self._build_ui()

        # One-time tidy-up of transcripts saved before clutter removal existed
        if db.get_setting(conn, "cleanup_v1_applied") is None:
            cleanup.clean_all(conn, cleanup.load_rules(conn))
            db.set_setting(conn, "cleanup_v1_applied", "1")

        saved = db.get_setting(conn, "current_library_id")
        if saved:
            self.library_id = int(saved)
            self.refresh_library()
        self.refresh_header_stats()
        self._update_enabled()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 12)
        outer.setSpacing(14)

        # Header: title + action buttons
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("📚 Study Guide")
        title.setObjectName("AppTitle")
        self.tagline = QLabel("Let's turn your slides into something fun to learn!")
        self.tagline.setObjectName("Tagline")
        titles.addWidget(title)
        titles.addWidget(self.tagline)
        header.addLayout(titles)
        header.addSpacing(24)

        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for view, text in (("library", "📚  Library"), ("flashcards", "🃏  Flashcards")):
            nav = button(text, "Nav")
            nav.setCheckable(True)
            nav.clicked.connect(lambda _=False, v=view: self.show_view(v))
            self.nav_group.addButton(nav)
            self.nav_buttons[view] = nav
            header.addWidget(nav)
        self.nav_buttons["library"].setChecked(True)
        header.addStretch(1)

        self.streak_stat = QLabel()
        self.streak_stat.setObjectName("HeaderStat")
        self.xp_stat = QLabel()
        self.xp_stat.setObjectName("HeaderStat")
        header.addWidget(self.streak_stat)
        header.addWidget(self.xp_stat)
        header.addSpacing(8)

        self.choose_button = button("📁  Choose Folder", "Plain")
        self.choose_button.clicked.connect(self.choose_folder)
        self.refresh_button = button("🔄  Refresh", "Sky")
        self.refresh_button.setShortcut(QKeySequence.Refresh)
        self.refresh_button.setToolTip("Look for new slides (⌘R)")
        self.refresh_button.clicked.connect(self.refresh_library)
        self.ocr_button = button("✨  Read New Slides", "Primary")
        self.ocr_button.setToolTip("Read the text on every slide that doesn't have any yet")
        self.ocr_button.clicked.connect(self.transcribe_pending)
        self.ignore_button = button("🧹  Ignore Text", "Plain")
        self.ignore_button.setToolTip("Remove repeated lines like copyright footers from transcripts")
        self.ignore_button.clicked.connect(self.edit_ignore_rules)
        for btn in (self.choose_button, self.ignore_button, self.refresh_button, self.ocr_button):
            header.addWidget(btn)
        outer.addLayout(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_welcome())
        self.pages.addWidget(self._build_library_page())
        self.flashcards_page = FlashcardsPage(self.conn, lambda: self.library_id)
        self.flashcards_page.progress_changed.connect(self.refresh_header_stats)
        self.flashcards_page.open_library.connect(lambda: self.show_view("library"))
        self.pages.addWidget(self.flashcards_page)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        if self.ocr_engine is None:
            self.statusBar().showMessage(
                "ℹ️  Automatic text reading needs macOS. You can still type transcripts by hand."
            )

    def _build_welcome(self) -> QWidget:
        frame, layout = card()
        layout.addStretch(1)
        for text, name in (
            ("📚✨", "WelcomeEmoji"),
            ("Welcome to Study Guide!", "WelcomeTitle"),
            (
                "Pick the folder where you keep your slide screenshots.\n"
                "Each subfolder becomes a topic. Your images are only read, never changed.",
                "WelcomeText",
            ),
        ):
            label = QLabel(text)
            label.setObjectName(name)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        start = button("📁  Choose my study folder", "Big")
        start.clicked.connect(self.choose_folder)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(start)
        row.addStretch(1)
        layout.addSpacing(10)
        layout.addLayout(row)
        layout.addStretch(2)
        return frame

    def _build_library_page(self) -> QWidget:
        # Left: progress + topics
        left, left_layout = card("Your Topics")
        self.progress_text = QLabel()
        self.progress_text.setObjectName("ProgressText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(18)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("FolderPath")
        self.folder_label.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.progress_text)
        left_layout.addWidget(self.progress_bar)
        left_layout.addSpacing(4)
        left_layout.addWidget(self.tree, 1)
        left_layout.addWidget(self.folder_label)

        # Middle: the slide
        middle, middle_layout = card("🖼️  Slide")
        self.image_view = ImageView()
        middle_layout.addWidget(self.image_view, 1)

        # Right: transcript
        right, right_layout = card("📝  Transcript")
        chip_row = QHBoxLayout()
        self.topic_chip = QLabel()
        self.topic_chip.setObjectName("Chip")
        self.topic_chip.hide()
        chip_row.addWidget(self.topic_chip)
        chip_row.addStretch(1)
        self.source_label = QLabel("No slide selected")
        self.source_label.setObjectName("SlideName")
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label = QLabel()
        self.status_label.setObjectName("StatusPill")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "The text from this slide shows up here. Fix any mistakes. Your edits are kept!"
        )
        self.editor.modificationChanged.connect(lambda _: self._update_enabled())

        self.save_button = button("💾  Save", "Primary")
        self.save_button.setShortcut(QKeySequence.Save)
        self.save_button.clicked.connect(self.save_current)
        self.revert_button = button("↩️  Undo", "Plain")
        self.revert_button.setToolTip("Throw away changes you haven't saved")
        self.revert_button.clicked.connect(self._load_transcript)
        self.reread_button = button("🔍  Re-read", "Purple")
        self.reread_button.setToolTip("Read the text from this slide's image again")
        self.reread_button.clicked.connect(self.reread_current)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)
        buttons.addWidget(self.reread_button)

        right_layout.addLayout(chip_row)
        right_layout.addWidget(self.source_label)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.editor, 1)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        for widget in (left, middle, right):
            splitter.addWidget(widget)
        splitter.setSizes([300, 580, 440])
        return splitter

    def _update_enabled(self) -> None:
        has_library = self.library_id is not None
        has_image = self.current_image_id is not None
        busy = self._ocr_thread is not None
        in_library = has_library and self.view == "library"
        if not has_library:
            self.pages.setCurrentIndex(0)
        else:
            self.pages.setCurrentIndex(1 if self.view == "library" else 2)
        for nav in self.nav_buttons.values():
            nav.setVisible(has_library)
        self.streak_stat.setVisible(has_library)
        self.xp_stat.setVisible(has_library)
        self.refresh_button.setVisible(in_library)
        self.ocr_button.setVisible(in_library)
        self.ignore_button.setVisible(in_library)
        self.ignore_button.setEnabled(not busy)
        self.choose_button.setVisible(in_library or not has_library)
        self.refresh_button.setEnabled(not busy)
        self.ocr_button.setEnabled(self.ocr_engine is not None and not busy)
        self.choose_button.setEnabled(not busy)
        self.editor.setEnabled(has_image)
        modified = has_image and self.editor.document().isModified()
        self.save_button.setEnabled(modified)
        self.revert_button.setEnabled(modified)
        self.reread_button.setEnabled(has_image and self.ocr_engine is not None and not busy)

    # ---------------------------------------------------------- navigation
    def show_view(self, view: str) -> None:
        if view != "library":
            self._autosave()
        self.view = view
        self.nav_buttons[view].setChecked(True)
        self.statusBar().clearMessage()
        if view == "flashcards" and not self.flashcards_page.in_round():
            self.flashcards_page.show_home()
        elif view == "library" and self.library_id is not None:
            self._populate_tree()
        self._update_enabled()
        self.refresh_header_stats()

    def refresh_header_stats(self) -> None:
        streak, _ = progress.streaks(self.conn)
        lvl = progress.level_for(progress.total_xp(self.conn))
        self.streak_stat.setText(f"🔥 {streak}")
        self.streak_stat.setToolTip(f"{streak}-day study streak")
        self.xp_stat.setText(f"⭐ Level {lvl.level}")
        self.xp_stat.setToolTip(f"{lvl.into_level}/{lvl.needed} XP to the next level")

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
        self.show_view("library")

    def edit_ignore_rules(self) -> None:
        self._autosave()
        dialog = IgnoreTextDialog(self.conn, self)
        if dialog.exec():
            n = dialog.changed_count
            self._populate_tree()
            if self.current_image_id is not None:
                self._load_transcript()
            self.statusBar().showMessage(
                f"🧹  Tidied up {n} transcript{'s' if n != 1 else ''}." if n
                else "🧹  Saved. New readings will skip those lines."
            )

    def refresh_library(self) -> None:
        if self.library_id is None:
            return
        self._autosave()
        root = library.library_root(self.conn, self.library_id)
        self.folder_label.setText(f"📂 {root}")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = library.scan_library(self.conn, self.library_id)
        except FileNotFoundError as exc:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage(f"😕  {exc}")
            QMessageBox.warning(
                self,
                "Study folder not found",
                f"{exc}\n\nIf it moved, use “Choose Folder” to pick it again. "
                "Your transcripts are still saved.",
            )
            self._populate_tree()
            self._update_enabled()
            return
        QApplication.restoreOverrideCursor()
        self._populate_tree()
        prefix = "🎉  " if result.added or result.restored else "✅  "
        self.statusBar().showMessage(prefix + result.summary())
        self._update_enabled()

    def _populate_tree(self) -> None:
        selected = self.current_image_id
        self.tree.blockSignals(True)
        self.tree.clear()
        self._topic_colors = {}
        select_item = None
        total = done_total = 0
        topic_font = self.tree.font()
        topic_font.setBold(True)
        for index, topic in enumerate(library.list_topics(self.conn, self.library_id)):
            color = theme.topic_color(index)
            self._topic_colors[topic["name"]] = color
            count = topic["image_count"] or 0
            done = topic["transcribed_count"] or 0
            total += count
            done_total += done
            label = f"{topic['name']}   {done}/{count}" + ("  ⭐" if count and done == count else "")
            topic_item = QTreeWidgetItem([label])
            topic_item.setIcon(0, theme.topic_icon(color, topic["name"]))
            topic_item.setFont(0, topic_font)
            topic_item.setFlags(topic_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(topic_item)
            for img in library.list_images(self.conn, topic["id"]):
                name = img["rel_path"].split("/", 1)[1]
                if img["transcript"]:
                    stale = img["ocr_sha256"] and img["ocr_sha256"] != img["sha256"]
                    marker = "⚠️" if stale else ("✏️" if img["edited"] else "✅")
                else:
                    marker = "⚪"
                item = QTreeWidgetItem([f"{marker}  {name}"])
                item.setData(0, IMAGE_ROLE, img["id"])
                item.setToolTip(0, img["rel_path"])
                topic_item.addChild(item)
                if img["id"] == selected:
                    select_item = item
            topic_item.setExpanded(True)
        self.tree.blockSignals(False)

        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done_total)
        if total == 0:
            self.progress_text.setText("No slides found yet")
        elif done_total == total:
            self.progress_text.setText(f"🌟 All {total} slides ready!")
        else:
            self.progress_text.setText(f"{done_total} of {total} slides ready")

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
            self.topic_chip.hide()
            self.source_label.setText("No slide selected")
            self.status_label.hide()
            self.editor.clear()
            self.editor.document().setModified(False)
            self._update_enabled()
            return
        row = library.get_image(self.conn, self.current_image_id)
        path = Path(row["root_path"]) / row["rel_path"]
        self.image_view.show_image(path)
        color = self._topic_colors.get(row["topic_name"], theme.PURPLE)
        self.topic_chip.setText(row["topic_name"])
        self.topic_chip.setStyleSheet(f"background: {color};")
        self.topic_chip.setToolTip(f"Topic: {row['topic_name']}")
        self.topic_chip.show()
        self.source_label.setText(row["rel_path"].split("/", 1)[1])
        self.source_label.setToolTip(f"From {row['rel_path']}")
        self._load_transcript()

    def _set_status(self, kind: str, text: str) -> None:
        bg, fg = theme.STATUS_STYLES[kind]
        self.status_label.setStyleSheet(f"background: {bg}; color: {fg};")
        self.status_label.setText(text)
        self.status_label.show()

    def _load_transcript(self) -> None:
        if self.current_image_id is None:
            return
        tr = transcripts.get_transcript(self.conn, self.current_image_id)
        row = library.get_image(self.conn, self.current_image_id)
        self.editor.setPlainText(tr["text"] if tr else "")
        self.editor.document().setModified(False)
        if tr is None:
            self._set_status("none", "⚪  No text yet. Click “Read New Slides” or type it in.")
        elif tr["ocr_sha256"] and tr["ocr_sha256"] != row["sha256"]:
            self._set_status("stale", "⚠️  This image changed since its text was read. Try “Re-read”.")
        elif tr["edited"]:
            self._set_status("edited", "✏️  Edited by you. Nice work keeping it accurate!")
        else:
            self._set_status("ocr", "✅  Read automatically. Give it a quick check for typos.")
        self._update_enabled()

    def save_current(self) -> None:
        if self.current_image_id is None:
            return
        transcripts.save_transcript(self.conn, self.current_image_id, self.editor.toPlainText())
        self._load_transcript()
        self._populate_tree()
        self.statusBar().showMessage("💾  Saved! Your fix is kept safe.", 3000)

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
            self.statusBar().showMessage("🌟  Every slide already has text. You're all set!")
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
            lambda done, total: self.statusBar().showMessage(f"🔍  Reading slides… {done}/{total}")
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
            self.statusBar().showMessage(
                f"😕  Done, but {len(self._ocr_failures)} slide(s) couldn't be read."
            )
            QMessageBox.warning(
                self, "Some slides couldn't be read", "\n".join(self._ocr_failures[:10])
            )
        else:
            self.statusBar().showMessage("🎉  All done! Check the transcripts for any typos.")
        self._update_enabled()

    # ---------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802
        self._autosave()
        if self._ocr_thread is not None:
            self._ocr_worker.stop_requested = True
            self._ocr_thread.quit()
            self._ocr_thread.wait()
        super().closeEvent(event)
