"""HTTP access to gutenberg.org. Plain GETs, no authentication."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import httpx

CATALOG_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
USER_AGENT = "gutenberg-tui/0.1 (+https://github.com/simontjell/gutenberg-tui)"

Progress = Callable[[int, int | None], None]


class BookNotAvailable(Exception):
    """The book has no plain-text edition."""


def book_text_url(book_id: int) -> str:
    return f"https://www.gutenberg.org/ebooks/{book_id}.txt.utf-8"


def _download(url: str, dest: Path, progress: Progress | None = None) -> Path:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.Client(follow_redirects=True, timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        with client.stream("GET", url) as response:
            if response.status_code == 404:
                raise BookNotAvailable(url)
            response.raise_for_status()
            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total else None
            done = 0
            with open(tmp, "wb") as handle:
                for chunk in response.iter_bytes(65536):
                    handle.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total_bytes)
    tmp.replace(dest)
    return dest


def fetch_catalog(dest: Path, progress: Progress | None = None) -> Path:
    return _download(CATALOG_URL, dest, progress)


def fetch_book(book_id: int, dest: Path, progress: Progress | None = None) -> Path:
    return _download(book_text_url(book_id), dest, progress)


def read_book(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
