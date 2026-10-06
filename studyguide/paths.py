"""Where the app keeps its own data.

The app never writes into your study folder. Everything it creates (database,
settings) lives in a separate per-user data folder:

* macOS:  ~/Library/Application Support/StudyGuide
* other:  ~/.local/share/StudyGuide (only used for development/testing)

Set the STUDYGUIDE_DATA_DIR environment variable to use a different folder
(the tests do this so they never touch your real data).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "StudyGuide"
DB_FILENAME = "studyguide.sqlite3"


def data_dir() -> Path:
    override = os.environ.get("STUDYGUIDE_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / DB_FILENAME
