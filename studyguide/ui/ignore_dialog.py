"""A small window for choosing which repeated text to drop from transcripts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from .. import cleanup
from .widgets import button, label


class IgnoreTextDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.changed_count = 0
        self.setWindowTitle("Text to ignore")
        self.setMinimumSize(620, 560)
        rules = cleanup.load_rules(conn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)
        layout.addWidget(label("🧹  Text to ignore", "HeroTitle"))
        layout.addWidget(label(
            "Lines that repeat on every slide, like a copyright footer, get in the way of "
            "studying. Matching lines are removed from your transcripts and won't become "
            "flashcards. Your images are never changed.",
            "HeroText", wrap=True))

        self.builtin = QCheckBox("Remove slide footers and copyright notices (recommended)")
        self.builtin.setChecked(rules.builtin)
        self.builtin.toggled.connect(self._update_preview)
        layout.addWidget(self.builtin)
        hint = label("Removes the Professor Messer footer (“https://ProfessorMesser.com © 2025 Messer "
                     "Studios, LLC”) even when the text reader garbles it, plus copyright notices like "
                     "“© 2024 …” or “All rights reserved”. Real content that just mentions copyright "
                     "is kept.", "Muted", wrap=True)
        hint.setContentsMargins(30, 0, 0, 0)
        layout.addWidget(hint)

        layout.addWidget(label("Also remove any line containing (one per line):", "CardTitle"))
        self.phrases = QPlainTextEdit("\n".join(rules.phrases))
        self.phrases.setPlaceholderText("For example:\nMesser Studios\nCompTIA A+ Core 1")
        self.phrases.setFixedHeight(120)
        self.phrases.textChanged.connect(self._update_preview)
        layout.addWidget(self.phrases)

        self.preview = label("", "ProgressText", wrap=True)
        layout.addWidget(self.preview)
        self.examples = label("", "Muted", wrap=True)
        layout.addWidget(self.examples)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        self.undo_button = button("↩️  Undo last cleanup", "Plain")
        self.undo_button.setToolTip("Put transcripts back the way they were before the last cleanup")
        self.undo_button.clicked.connect(self.undo)
        self.undo_button.setVisible(cleanup.last_cleanup_batch(conn) is not None)
        buttons.addWidget(self.undo_button)
        buttons.addStretch(1)
        cancel = button("Cancel", "Plain")
        cancel.clicked.connect(self.reject)
        self.save_button = button("🧹  Save and clean up", "Primary")
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self._update_preview()

    def rules(self) -> cleanup.Rules:
        phrases = [p.strip() for p in self.phrases.toPlainText().splitlines() if p.strip()]
        return cleanup.Rules(builtin=self.builtin.isChecked(), phrases=phrases)

    def _update_preview(self) -> None:
        changes = cleanup.preview_all(self.conn, self.rules())
        if changes:
            n = len(changes)
            self.preview.setText(f"✨ {n} transcript{'s' if n != 1 else ''} will be tidied up. "
                                 "A backup is kept so you can undo it.")
            lines = []
            for _, rel_path, removed in changes[:3]:
                lines.append(f"• {rel_path.split('/', 1)[-1]}: removes “{removed[0].strip()}”")
            self.examples.setText("\n".join(lines))
        else:
            self.preview.setText("No saved transcripts contain matching lines right now. "
                                 "New readings will be cleaned automatically.")
            self.examples.setText("")

    def undo(self) -> None:
        self.changed_count = -cleanup.undo_last_cleanup(self.conn)
        self.accept()

    def save(self) -> None:
        rules = self.rules()
        cleanup.save_rules(self.conn, rules)
        self.changed_count = cleanup.clean_all(self.conn, rules)
        self.accept()
