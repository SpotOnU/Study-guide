"""Offer to replace old fragment-based cards with new, explained questions."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from .. import flashcards
from ..generators import SOURCE_CONTEXT
from .widgets import button, card, label

PREVIEW_LIMIT = 12


class UpgradeDialog(QDialog):
    def __init__(self, conn, library_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.library_id = library_id
        self.result_summary = None
        self.setWindowTitle("Upgrade your flashcards")
        self.setMinimumSize(860, 680)

        status = flashcards.old_cards_status(conn, library_id)
        preview = flashcards.preview_items(conn, library_id, only_waiting=True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(12)
        outer.addWidget(label("🛠️  Upgrade your flashcards", "HeroTitle"))
        outer.addWidget(label(
            f"{status.total} older cards were made by copying slide fragments and blanking a word. "
            f"{status.paused} of them are paused and kept out of your rounds because they fail the new "
            f"quality checks. New questions test the concept, explain the answer and show where it came "
            f"from. Your review history and your slide images are not touched.",
            "HeroText", wrap=True))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(10)

        col.addWidget(label("Examples of paused cards", "SectionTitle"))
        for c in status.examples:
            frame, fl = card(name="MissedCard")
            fl.setSpacing(3)
            fl.addWidget(label(c["front"].rpartition("\n\n")[2], "MissedFront", wrap=True))
            fl.addWidget(label(f"Answer: {c['back']}", "Muted", wrap=True))
            fl.addWidget(label("Why it's paused: " + c["paused"], "PausedReason", wrap=True))
            col.addWidget(frame)

        col.addWidget(label(
            f"Preview: {len(preview.items)} new questions from the same slides", "SectionTitle"))
        if preview.skipped_slides:
            col.addWidget(label(
                f"{len(preview.skipped_slides)} slide(s) don't have enough information for a good "
                "question, so they're skipped rather than given a weak card.", "Muted", wrap=True))
        for item in preview.items[:PREVIEW_LIMIT]:
            col.addWidget(self._item_card(item))
        if len(preview.items) > PREVIEW_LIMIT:
            col.addWidget(label(f"…and {len(preview.items) - PREVIEW_LIMIT} more.", "Muted"))
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        later = button("Not now", "Plain")
        later.clicked.connect(self.reject)
        self.go = button("✨  Regenerate from my slides", "Primary")
        self.go.clicked.connect(self.regenerate)
        self.go.setEnabled(status.total > 0)
        buttons.addWidget(later)
        buttons.addWidget(self.go)
        outer.addLayout(buttons)

    @staticmethod
    def _item_card(item) -> QWidget:
        frame, fl = card(name="MissedCard")
        fl.setSpacing(4)
        head = QHBoxLayout()
        tag = ("🎓 Added CompTIA A+ Core 2 context" if item.source == SOURCE_CONTEXT
               else "📘 From your slide")
        head.addWidget(label(tag, "ContextTag"))
        head.addStretch(1)
        head.addWidget(label(item.kind.replace("_", " "), "Muted"))
        fl.addLayout(head)
        fl.addWidget(label(item.prompt, "MissedFront", wrap=True))
        if item.options:
            opts = label("<br>".join(f"• {html.escape(o)}" for o in item.options), "Options", wrap=True)
            opts.setTextFormat(Qt.RichText)
            fl.addWidget(opts)
        fl.addWidget(label(f"✅  {item.answer}", "MissedAnswer", wrap=True))
        fl.addWidget(label(item.explanation, "Explanation", wrap=True))
        where = "Slide mentions it" if item.source == SOURCE_CONTEXT else "Slide line"
        fl.addWidget(label(f"{where}: “{item.slide_support}”", "Context", wrap=True))
        return frame

    def regenerate(self) -> None:
        self.result_summary = flashcards.regenerate_old_cards(self.conn, self.library_id)
        self.accept()
