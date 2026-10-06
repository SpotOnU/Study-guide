"""Start the Study Guide desktop app."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import db, paths
from .ocr import default_engine
from .ui import theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Study Guide")
    theme.apply(app)
    conn = db.connect(paths.db_path())
    window = MainWindow(conn, default_engine())
    window.show()
    return app.exec()
