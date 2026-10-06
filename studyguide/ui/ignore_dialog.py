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

        self.builtin = QCheckBox("Remove copyright lines and bare web addresses (recommended)")
        self.builtin.setChecked(rules.builtin)
        self.builtin.toggled.connect(self._update_preview)
        layout.addWidget(self.builtin)
        hint = label("Catches lines with ©, “Copyright” or “All rights reserved”, and lines that are "
                     "only a link such as https://ProfessorMesser.com.", "Muted", wrap=True)
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
        layout.addStretch(1)

        buttons = QHBoxLayout()
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
        n = cleanup.count_affected(self.conn, self.rules())
        if n:
            self.preview.setText(f"✨ {n} transcript{'s' if n != 1 else ''} will be tidied up.")
        else:
            self.preview.setText("No saved transcripts contain matching lines right now. "
                                 "New readings will be cleaned automatically.")

    def save(self) -> None:
        rules = self.rules()
        cleanup.save_rules(self.conn, rules)
        self.changed_count = cleanup.clean_all(self.conn, rules)
        self.accept()
