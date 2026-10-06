"""Colours, fonts and the stylesheet for a bright, friendly look."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FAMILY = "Nunito"

# Base colours
CREAM = "#FFF8EC"
CARD = "#FFFFFF"
CARD_BORDER = "#F1E4CF"
INK = "#2D2A4A"
MUTED = "#7A7596"

GREEN, GREEN_DARK, GREEN_SOFT = "#20A35A", "#17803F", "#E3F8EA"
PURPLE, PURPLE_DARK, PURPLE_SOFT = "#6C4BF4", "#4F31CC", "#EEE9FF"
SKY, SKY_DARK, SKY_SOFT = "#1C9AD6", "#147AAB", "#E2F4FD"
SUNNY, SUNNY_DARK, SUNNY_SOFT = "#FFC83D", "#E0A100", "#FFF4D6"
CORAL, CORAL_DARK, CORAL_SOFT = "#F25F5C", "#C94441", "#FFE6E5"

# Each topic gets its own colour, in this order.
TOPIC_COLORS = ["#6C4BF4", "#F25F5C", "#1C9AD6", "#FF8A1F", "#14B8A6", "#E64CA8", "#E0A100"]


def topic_color(index: int) -> str:
    return TOPIC_COLORS[index % len(TOPIC_COLORS)]


def topic_icon(color: str, letter: str, size: int = 28) -> QIcon:
    """A coloured circle with the topic's first letter."""
    pixmap = QPixmap(size * 2, size * 2)  # 2x for sharp rendering on Retina
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    font = QFont(FONT_FAMILY, 11)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(0, 0, size, size, Qt.AlignCenter, (letter or "?")[:1].upper())
    painter.end()
    return QIcon(pixmap)


def load_fonts() -> None:
    for path in FONT_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(path))


def apply(app: QApplication) -> None:
    """Use one consistent light theme, regardless of the system dark/light mode."""
    load_fonts()
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(CREAM))
    palette.setColor(QPalette.WindowText, QColor(INK))
    palette.setColor(QPalette.Base, QColor(CARD))
    palette.setColor(QPalette.AlternateBase, QColor(CREAM))
    palette.setColor(QPalette.Text, QColor(INK))
    palette.setColor(QPalette.Button, QColor(CARD))
    palette.setColor(QPalette.ButtonText, QColor(INK))
    palette.setColor(QPalette.Highlight, QColor(PURPLE))
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
    palette.setColor(QPalette.ToolTipBase, QColor(INK))
    palette.setColor(QPalette.ToolTipText, QColor("white"))
    app.setPalette(palette)
    font = QFont(FONT_FAMILY, 13)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def _chunky(name: str, bg: str, dark: str, fg: str = "white") -> str:
    """A rounded button with a darker bottom edge that 'presses down' when clicked."""
    return f"""
    QPushButton#{name} {{
        background: {bg}; color: {fg};
        border: 2px solid {dark}; border-bottom: 5px solid {dark};
        border-radius: 14px; padding: 7px 16px 5px 16px;
        font-weight: 800; font-size: 14px;
    }}
    QPushButton#{name}:hover {{ background: {dark}; }}
    QPushButton#{name}:pressed {{ border-bottom-width: 2px; margin-top: 3px; }}
    QPushButton#{name}:disabled {{
        background: #ECE8E1; color: #ADA8BC; border-color: #DDD7CC;
    }}
    """


STYLESHEET = f"""
QWidget {{ color: {INK}; font-family: "{FONT_FAMILY}"; }}
QMainWindow, QWidget#Root {{ background: {CREAM}; }}

QFrame#Card {{
    background: {CARD}; border: 2px solid {CARD_BORDER}; border-radius: 22px;
}}
QLabel#CardTitle {{ font-size: 17px; font-weight: 900; }}
QLabel#AppTitle {{ font-size: 26px; font-weight: 900; color: {PURPLE}; }}
QLabel#Tagline {{ font-size: 14px; color: {MUTED}; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; font-weight: 600; }}
QLabel#FolderPath {{ color: {MUTED}; font-size: 12px; }}
QLabel#ProgressText {{ font-weight: 800; font-size: 14px; }}
QLabel#SlideName {{ font-size: 16px; font-weight: 800; }}
QLabel#Chip {{
    border-radius: 12px; padding: 3px 12px; font-weight: 800; font-size: 13px; color: white;
}}
QLabel#StatusPill {{ border-radius: 12px; padding: 7px 12px; font-weight: 700; }}
QLabel#Placeholder {{ color: {MUTED}; font-size: 16px; font-weight: 700; }}

QLabel#WelcomeEmoji {{ font-size: 72px; }}
QLabel#WelcomeTitle {{ font-size: 32px; font-weight: 900; color: {PURPLE}; }}
QLabel#WelcomeText {{ font-size: 16px; color: {MUTED}; font-weight: 600; }}

{_chunky("Primary", GREEN, GREEN_DARK)}
{_chunky("Purple", PURPLE, PURPLE_DARK)}
{_chunky("Sky", SKY, SKY_DARK)}
{_chunky("Plain", CARD, "#DDD3C2", INK)}
QPushButton#Plain:hover {{ background: {CREAM}; }}
{_chunky("Big", GREEN, GREEN_DARK)}
QPushButton#Big {{ font-size: 18px; padding: 12px 28px 10px 28px; border-radius: 18px; }}

QProgressBar {{
    background: #F2ECE2; border: none; border-radius: 9px; height: 18px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {GREEN}; border-radius: 9px; }}

QTreeWidget {{
    background: transparent; border: none; font-size: 14px; outline: 0;
    show-decoration-selected: 0; selection-background-color: transparent;
}}
QTreeWidget::item {{
    padding: 6px 6px; border-radius: 10px; margin: 1px 0;
}}
QTreeWidget::item:hover {{ background: {CREAM}; }}
QTreeWidget::item:selected {{ background: {PURPLE_SOFT}; color: {PURPLE_DARK}; font-weight: 800; }}
QTreeWidget::branch, QTreeWidget::branch:selected {{ background: transparent; }}

QPlainTextEdit {{
    background: #FFFDF8; border: 2px solid {CARD_BORDER}; border-radius: 16px;
    padding: 10px; font-size: 15px; selection-background-color: {PURPLE_SOFT};
    selection-color: {INK};
}}
QPlainTextEdit:focus {{ border-color: {PURPLE}; }}
QPlainTextEdit:disabled {{ background: #FAF6EE; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent; width: 10px; height: 10px; margin: 2px;
}}
QScrollBar::handle {{ background: #E3D8C6; border-radius: 5px; min-height: 30px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QSplitter::handle {{ background: transparent; width: 14px; }}

QStatusBar {{
    background: {CARD}; border-top: 2px solid {CARD_BORDER};
    font-weight: 700; padding: 4px 10px;
}}
QToolTip {{ background: {INK}; color: white; border: none; padding: 6px; border-radius: 6px; }}
QMessageBox {{ background: {CARD}; }}
"""

# Visual styles for the transcript status pill: (background, text colour)
STATUS_STYLES = {
    "none": ("#F2ECE2", MUTED),
    "ocr": (GREEN_SOFT, GREEN_DARK),
    "edited": (SUNNY_SOFT, "#8A6300"),
    "stale": (CORAL_SOFT, CORAL_DARK),
}
