"""Small building blocks shared by the app's screens."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QLayout, QPushButton, QVBoxLayout


def card(title: Optional[str] = None, name: str = "Card") -> Tuple[QFrame, QVBoxLayout]:
    """A white rounded panel, optionally with a bold title."""
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("CardTitle")
        layout.addWidget(label)
    return frame, layout


def button(text: str, style: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName(style)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def label(text: str = "", name: Optional[str] = None, wrap: bool = False,
          align: Optional[Qt.AlignmentFlag] = None) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def chip(text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Chip")
    lbl.setStyleSheet(f"background: {color};")
    return lbl


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
