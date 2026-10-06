import hashlib
import os
import struct
import zlib
from pathlib import Path

import pytest

from studyguide import db


def make_png(path: Path, shade: int = 0, size: int = 4) -> None:
    """Write a small valid greyscale PNG (used only to build test fixtures)."""
    raw = b"".join(b"\x00" + bytes([shade]) * size for _ in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def snapshot(root: Path) -> dict:
    """Every file and folder under root with its content hash, size, mode and mtime."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            st = path.stat()
            entry = (st.st_mode, st.st_size, st.st_mtime_ns)
            if path.is_file():
                entry += (hashlib.sha256(path.read_bytes()).hexdigest(),)
            state[path.relative_to(root).as_posix()] = entry
    return state


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Never let tests touch the real app data folder."""
    data = tmp_path / "appdata"
    monkeypatch.setenv("STUDYGUIDE_DATA_DIR", str(data))
    return data


@pytest.fixture
def study_root(tmp_path) -> Path:
    root = tmp_path / "Study"
    make_png(root / "Biology" / "slide01.png", 10)
    make_png(root / "Biology" / "slide02.PNG", 20)
    make_png(root / "Biology" / "Week 2" / "cells.png", 30)
    make_png(root / "Chemistry" / "atoms.png", 40)
    (root / "Chemistry" / "notes.txt").write_text("not an image")
    make_png(root / "Chemistry" / ".hidden.png", 50)
    make_png(root / ".git-like" / "ignored.png", 60)
    (root / "Empty Topic").mkdir()
    make_png(root / "loose.png", 70)
    return root


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.sqlite3")
    yield connection
    connection.close()
