"""The user's personal shelf of saved books."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from gutenberg_tui.catalog import Book, _row_to_book, _COLUMNS


@dataclass(frozen=True)
class ShelfEntry:
    book: Book
    added_at: str
    position: int


class Shelf:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, book_id: int) -> bool:
        """Add a book. Returns False if it was already on the shelf."""
        with self.conn:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO shelf (book_id, added_at) VALUES (?, ?)",
                (book_id, datetime.now(UTC).isoformat(timespec="seconds")),
            )
        return cursor.rowcount == 1

    def remove(self, book_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM shelf WHERE book_id = ?", (book_id,))

    def contains(self, book_id: int) -> bool:
        return (
            self.conn.execute("SELECT 1 FROM shelf WHERE book_id = ?", (book_id,)).fetchone()
            is not None
        )

    def list(self) -> list[ShelfEntry]:
        rows = self.conn.execute(
            f"""
            SELECT {', '.join('b.' + c for c in _COLUMNS.split(', '))},
                   s.added_at, s.position
            FROM shelf s JOIN books b ON b.id = s.book_id
            ORDER BY s.added_at DESC
            """
        ).fetchall()
        return [
            ShelfEntry(book=_row_to_book(row), added_at=row["added_at"], position=row["position"])
            for row in rows
        ]

    def set_position(self, book_id: int, position: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE shelf SET position = ? WHERE book_id = ?", (position, book_id)
            )

    def get_position(self, book_id: int) -> int:
        row = self.conn.execute(
            "SELECT position FROM shelf WHERE book_id = ?", (book_id,)
        ).fetchone()
        return row["position"] if row else 0
