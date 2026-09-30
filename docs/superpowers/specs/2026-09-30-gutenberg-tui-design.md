# Gutenberg TUI — design

A terminal application for browsing, searching and reading Project Gutenberg
books, with a personal shelf of locally saved books. No authentication of any
kind against gutenberg.org (the site has none; nothing is sent besides plain
HTTP GETs).

## Goals

- Browse the catalogue by bookshelf and by language.
- Search the catalogue (title, author, subject, bookshelf) with instant results.
- Read a book in the terminal with a comfortable, reflowing text view.
- Search inside the open book and jump between matches.
- Keep a personal shelf; every shelved book is stored locally and can be read
  offline, with the reading position remembered.

## Non-goals

- Accounts, logins, sync, or any interaction with gutenberg.org beyond GETs.
- Formats other than plain text (`.txt.utf-8`). EPUB/HTML rendering is out.
- Full-text search across the whole catalogue (only inside an open book).

## Stack

- Python 3.12+, managed with `uv`.
- [Textual](https://textual.textualize.io/) 8 for the TUI.
- `httpx` for HTTP, `sqlite3` (FTS5) for the catalogue index, `platformdirs`
  for the data directory.

## Data sources (gutenberg.org only)

| Purpose      | URL |
|--------------|-----|
| Catalogue    | `https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv` (~21 MB, ~79k rows) |
| Book text    | `https://www.gutenberg.org/ebooks/{id}.txt.utf-8` (302 → `cache/epub/{id}/pg{id}.txt`) |

The catalogue CSV columns: `Text#, Type, Issued, Title, Language, Authors,
Subjects, LoCC, Bookshelves`. Only rows with `Type == Text` are shown.

No third‑party API (e.g. Gutendex) is used, so the app depends on gutenberg.org
alone.

## Local storage

`platformdirs.user_data_dir("gutenberg-tui")`, typically
`~/.local/share/gutenberg-tui/`:

```
catalog.db      sqlite: catalogue + FTS index + shelf + reading positions
books/{id}.txt  downloaded book text (raw, as served)
```

### Schema

```sql
meta(key TEXT PRIMARY KEY, value TEXT);            -- catalog_updated_at
books(id INTEGER PRIMARY KEY, title, language, authors, subjects,
      bookshelves, issued);
books_fts USING fts5(title, authors, subjects, bookshelves,
      content='books', content_rowid='id');
shelf(book_id INTEGER PRIMARY KEY REFERENCES books(id),
      added_at TEXT, position INTEGER NOT NULL DEFAULT 0);
```

`position` is the index of the paragraph at the top of the reader viewport,
which is stable across terminal resizes.

## Modules

```
src/gutenberg_tui/
  __init__.py      main() entry point
  paths.py         data dir, db path, book path
  catalog.py       Catalog: import CSV → sqlite, search(), bookshelves(),
                   languages(), by_bookshelf(), by_language(), get()
  shelf.py         Shelf: add(), remove(), list(), set_position(), get_position()
  gutenberg.py     fetch_catalog(dest, progress), fetch_book(id, dest, progress)
  text.py          strip_boilerplate(), paragraphs(), wrap(), find()
  app.py           GutenbergApp + screens + BookView widget
```

`catalog.py`, `shelf.py`, `text.py` are pure and unit-tested. `gutenberg.py`
is thin over httpx. `app.py` holds all Textual code and is smoke-tested with
Textual's `Pilot`.

### catalog.py

- `Catalog(db_path)` opens/creates the sqlite db.
- `import_csv(path)` replaces the `books` table and rebuilds FTS in one
  transaction, stores `catalog_updated_at`.
- `search(query, limit=200) -> list[Book]`: tokenises the query, builds an
  FTS5 query where each token is a prefix match (`"tok"*`), ordered by
  `bm25(books_fts)`. Empty query → recent books.
- `bookshelves() -> list[(name, count)]`, `languages() -> list[(code, count)]`.
- `by_bookshelf(name)`, `by_language(code)`, `get(id)`.
- `Book` is a frozen dataclass (id, title, authors, language, subjects,
  bookshelves, issued).

### text.py

- `strip_boilerplate(raw)`: cut everything up to and including the
  `*** START OF THE PROJECT GUTENBERG EBOOK ... ***` line and from
  `*** END OF ...` onwards. If markers are missing, return the text unchanged.
- `paragraphs(text) -> list[str]`: split on blank lines; lines inside a
  paragraph are joined with single spaces, except paragraphs where every line
  is indented (verse / preformatted) which are kept line-for-line.
- `wrap(paragraphs, width) -> list[(para_index, line_text)]`.
- `find(paragraphs, needle) -> list[int]`: case-insensitive paragraph indices.

## UI

Textual app with a screen stack. Header shows the screen title, Footer shows
key bindings.

### MainScreen (search & results)

```
┌ Gutenberg ────────────────────────────────────────────┐
│ Search: [pride prejudice_______________________]       │
│ ▸ Pride and Prejudice — Austen, Jane            en    │
│   Pride and Prejudice, a play — ...             en    │
│ ...                                                    │
└────────────────────────────────────────────────────────┘
 / search  enter read  a add to shelf  i info  b browse  s shelf  r refresh catalog  q quit
```

- Typing in the input searches after a 150 ms debounce; results in an
  `OptionList`.
- `enter` opens the reader; `a` adds to the shelf (downloads the text);
  `i` shows a details modal (full title, authors, language, subjects,
  bookshelves, issued date, Gutenberg URL).
- On first start with no catalogue, a modal downloads and imports it with a
  progress bar. `r` re-downloads. If the catalogue is older than 7 days the
  app refreshes it in the background on start.

### BrowseScreen

Two-pane: left an `OptionList` of categories under a `Bookshelves | Languages`
tab, right the books in the selected category. Same book actions as
MainScreen.

### ShelfScreen

List of shelved books with `%` read and whether the file is present.
`enter` reads from the local file (no network), `d` removes (with the file),
`i` info.

### ReaderScreen

- `BookView(ScrollView)` renders wrapped lines with the Line API, so a 1 MB
  book costs nothing to display. Re-wraps on resize keeping the top paragraph.
- Keys: `j/k/↓/↑` line, `space/pgdn` `b/pgup` page, `g/G` start/end,
  `/` search in book, `n/N` next/previous match, `a` add to shelf,
  `q/esc` back. The subtitle shows `42%` and `match 3/17` during search.
- Search matches are highlighted in the text; the current match is scrolled
  to the top of the view.
- Position is saved to `shelf.position` on every scroll (throttled) and on
  exit, when the book is on the shelf.
- Book text is downloaded on open (with a loading indicator) unless the file
  exists locally; the download is always saved to `books/{id}.txt` so that a
  second open is offline.

## Error handling

- Network failures show a `notify(severity="error")` toast and leave the
  current screen usable; nothing is retried automatically.
- A book without a plain-text edition (HTTP 404) shows a toast naming the id.
- Malformed catalogue rows are skipped, not fatal.

## Testing

- `tests/test_text.py`: boilerplate stripping, paragraph splitting (prose and
  verse), wrapping, find.
- `tests/test_catalog.py`: import a small CSV fixture, search by prefix,
  bookshelves/languages counts, by_bookshelf.
- `tests/test_shelf.py`: add/remove/list/position.
- `tests/test_app.py`: Pilot smoke test — app starts with a pre-seeded db,
  typing a query lists results, opening the reader with a local file renders
  text, `/` + query highlights a match.
