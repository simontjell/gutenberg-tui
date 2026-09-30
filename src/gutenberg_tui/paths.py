"""Filesystem locations for local data."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "gutenberg-tui"


def data_dir() -> Path:
    override = os.environ.get("GUTENBERG_TUI_DATA")
    path = Path(override) if override else Path(user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "catalog.db"


def books_dir() -> Path:
    path = data_dir() / "books"
    path.mkdir(parents=True, exist_ok=True)
    return path


def book_path(book_id: int) -> Path:
    return books_dir() / f"{book_id}.txt"
