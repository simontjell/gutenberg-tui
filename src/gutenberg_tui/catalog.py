"""Catalogue of Gutenberg books, indexed in sqlite with FTS5."""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    authors TEXT NOT NULL,
    subjects TEXT NOT NULL,
    bookshelves TEXT NOT NULL,
    issued TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title, authors, subjects, bookshelves,
    content='books', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS shelf (
    book_id INTEGER PRIMARY KEY REFERENCES books(id),
    added_at TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    authors: str
    language: str
    subjects: str
    bookshelves: str
    issued: str

    @property
    def short_title(self) -> str:
        return self.title.split("\n", 1)[0]

    @property
    def url(self) -> str:
        return f"https://www.gutenberg.org/ebooks/{self.id}"

    def label(self) -> str:
        who = f" — {self.authors}" if self.authors else ""
        return f"{self.short_title}{who}"


def _row_to_book(row: sqlite3.Row) -> Book:
    return Book(
        id=row["id"],
        title=row["title"],
        authors=row["authors"],
        language=row["language"],
        subjects=row["subjects"],
        bookshelves=row["bookshelves"],
        issued=row["issued"],
    )


_TOKEN = re.compile(r"\w+", re.UNICODE)

_COLUMNS = "id, title, language, authors, subjects, bookshelves, issued"
_BOOK_COLUMNS = ", ".join(f"b.{column}" for column in _COLUMNS.split(", "))


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


class Catalog:
    BROWSE_LIMIT = 5000

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- import -------------------------------------------------------------

    def import_csv(self, path: Path | str) -> int:
        """Replace the catalogue with the rows of a pg_catalog.csv file."""
        rows = list(_read_csv(path))
        with self.conn:
            self.conn.execute("DELETE FROM books")
            self.conn.executemany(
                f"INSERT INTO books ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)", rows
            )
            self.conn.execute("INSERT INTO books_fts(books_fts) VALUES ('rebuild')")
            self.conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('catalog_updated_at', ?)",
                (datetime.now(UTC).isoformat(timespec="seconds"),),
            )
        return len(rows)

    def updated_at(self) -> datetime | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'catalog_updated_at'"
        ).fetchone()
        return datetime.fromisoformat(row["value"]) if row else None

    def is_empty(self) -> bool:
        return self.conn.execute("SELECT 1 FROM books LIMIT 1").fetchone() is None

    def count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM books").fetchone()[0]

    # -- queries ------------------------------------------------------------

    def get(self, book_id: int) -> Book | None:
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        return _row_to_book(row) if row else None

    def search(self, query: str, limit: int = 200) -> list[Book]:
        tokens = _TOKEN.findall(query)
        if not tokens:
            return self.recent(limit)
        match = " ".join(f'"{token}"*' for token in tokens)
        # Rank inside the FTS query itself: a correlated bm25() subquery
        # would run one full-text match per row and freeze on short prefixes.
        rows = self.conn.execute(
            f"""
            SELECT {_BOOK_COLUMNS}
            FROM books_fts JOIN books b ON b.id = books_fts.rowid
            WHERE books_fts MATCH ?
            ORDER BY bm25(books_fts, 10.0, 5.0, 1.0, 1.0)
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [_row_to_book(row) for row in rows]

    def recent(self, limit: int = 200) -> list[Book]:
        rows = self.conn.execute(
            f"SELECT {_COLUMNS} FROM books ORDER BY issued DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_book(row) for row in rows]

    def bookshelves(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for (shelves,) in self.conn.execute(
            "SELECT bookshelves FROM books WHERE bookshelves != ''"
        ):
            for name in shelves.split(";"):
                name = name.strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items(), key=lambda item: item[0].lower())

    def languages(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT language, count(*) AS n FROM books GROUP BY language ORDER BY n DESC"
        ).fetchall()
        return [(row["language"], row["n"]) for row in rows]

    def by_bookshelf(self, name: str, limit: int = BROWSE_LIMIT) -> list[Book]:
        rows = self.conn.execute(
            f"""
            SELECT {_COLUMNS} FROM books
            WHERE ';' || replace(bookshelves, '; ', ';') || ';' LIKE ?
            ORDER BY title LIMIT ?
            """,
            (f"%;{name};%", limit),
        ).fetchall()
        return [_row_to_book(row) for row in rows]

    def by_language(self, code: str, limit: int = BROWSE_LIMIT) -> list[Book]:
        rows = self.conn.execute(
            f"SELECT {_COLUMNS} FROM books WHERE language = ? ORDER BY title LIMIT ?",
            (code, limit),
        ).fetchall()
        return [_row_to_book(row) for row in rows]


def _read_csv(path: Path | str) -> Iterator[tuple]:
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                if row.get("Type") != "Text":
                    continue
                yield (
                    int(row["Text#"]),
                    row["Title"].strip(),
                    row["Language"].strip(),
                    row["Authors"].strip(),
                    row["Subjects"].strip(),
                    row["Bookshelves"].strip(),
                    row["Issued"].strip(),
                )
            except (KeyError, ValueError, TypeError):
                continue
