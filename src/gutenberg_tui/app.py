"""Textual application: screens and widgets."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.geometry import Size
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    ProgressBar,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from gutenberg_tui import gutenberg, paths, text
from gutenberg_tui.catalog import Book, Catalog, connect
from gutenberg_tui.shelf import Shelf

CATALOG_MAX_AGE = timedelta(days=7)


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------


class BookList(OptionList):
    """An OptionList of books, one line per book."""

    DEFAULT_CSS = """
    BookList { text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.books: list[Book] = []

    def set_books(self, books: list[Book], extra: dict[int, str] | None = None) -> None:
        self.books = books
        self.clear_options()
        options = []
        for book in books:
            prompt = Text(book.short_title)
            if book.authors:
                prompt.append(f" — {book.authors}", style="dim")
            prompt.append(f"  {book.language}", style="italic dim")
            if extra and book.id in extra:
                prompt.append(f"  {extra[book.id]}", style="bold green")
            options.append(Option(prompt, id=str(book.id)))
        self.add_options(options)
        if books:
            self.highlighted = 0

    @property
    def current(self) -> Book | None:
        if self.highlighted is None or not self.books:
            return None
        return self.books[self.highlighted]


class BookView(ScrollView):
    """Renders a book's paragraphs, wrapped to the widget width."""

    DEFAULT_CSS = """
    BookView {
        width: 1fr;
        height: 1fr;
        max-width: 92;
        padding: 0 1;
    }
    """

    class Scrolled(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.paras: list[str] = []
        self.lines: list[tuple[int, str]] = []
        self.needle = ""
        self.matches: list[int] = []
        self.match_index = -1
        self._wrap_width = 0
        self._pending_top: int | None = None

    # -- content -----------------------------------------------------------

    def set_paragraphs(self, paras: list[str], top_paragraph: int = 0) -> None:
        self.paras = paras
        self._pending_top = top_paragraph
        self._rewrap()

    def _rewrap(self) -> None:
        """Wrap to the current width, keeping the top paragraph in place.

        Does nothing until the widget has been laid out with a real width;
        ``on_resize`` calls back once it has.
        """
        width = self._text_width()
        if width <= 0:
            return
        top = self._pending_top if self._pending_top is not None else self.top_paragraph
        self._pending_top = None
        self._wrap_width = width
        self.lines = text.wrap(self.paras, width)
        self.virtual_size = Size(width, len(self.lines))
        self.scroll_to_paragraph(top)
        self.refresh()
        self.post_message(self.Scrolled())

    def _text_width(self) -> int:
        # Books always scroll, so reserve room for the vertical scrollbar.
        return self.size.width - self.styles.scrollbar_size_vertical

    def on_resize(self) -> None:
        if self.paras and self._text_width() != self._wrap_width:
            self._rewrap()

    # -- position ----------------------------------------------------------

    @property
    def top_paragraph(self) -> int:
        if not self.lines:
            return 0
        y = min(int(self.scroll_offset.y), len(self.lines) - 1)
        return self.lines[y][0]

    @property
    def percent(self) -> int:
        if not self.lines:
            return 0
        span = len(self.lines) - self.size.height
        if span <= 0:
            return 100
        return min(100, round(100 * self.scroll_offset.y / span))

    def scroll_to_paragraph(self, index: int) -> None:
        for y, (para, _) in enumerate(self.lines):
            if para >= index:
                self.scroll_to(y=y, animate=False, force=True)
                return
        self.scroll_end(animate=False)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self.post_message(self.Scrolled())

    # -- search ------------------------------------------------------------

    def set_needle(self, needle: str) -> int:
        self.needle = needle.strip()
        self.matches = text.find(self.paras, self.needle)
        self.match_index = -1
        self.refresh()
        if self.matches:
            # jump to the first match at or after the current position
            top = self.top_paragraph
            index = next((i for i, p in enumerate(self.matches) if p >= top), 0)
            self.goto_match(index)
        return len(self.matches)

    def goto_match(self, index: int) -> None:
        if not self.matches:
            return
        self.match_index = index % len(self.matches)
        self.scroll_to_paragraph(self.matches[self.match_index])
        self.refresh()

    def next_match(self) -> None:
        self.goto_match(self.match_index + 1)

    def previous_match(self) -> None:
        self.goto_match(self.match_index - 1)

    # -- rendering ---------------------------------------------------------

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        index = y + int(scroll_y)
        width = self.scrollable_content_region.width
        base = self.rich_style
        if index >= len(self.lines):
            return Strip.blank(width, base)
        para, line = self.lines[index]
        if self.needle and para in self.matches:
            segments = self._highlight(line, base, current=(self.matches[self.match_index] == para) if self.match_index >= 0 else False)
        else:
            segments = [Segment(line, base)]
        return Strip(segments).adjust_cell_length(width, base)

    def _highlight(self, line: str, base: Style, current: bool) -> list[Segment]:
        mark = base + Style(reverse=True, bold=current)
        needle = self.needle.lower()
        lower = line.lower()
        segments: list[Segment] = []
        pos = 0
        while True:
            hit = lower.find(needle, pos)
            if hit < 0:
                break
            if hit > pos:
                segments.append(Segment(line[pos:hit], base))
            segments.append(Segment(line[hit : hit + len(needle)], mark))
            pos = hit + len(needle)
        if pos < len(line):
            segments.append(Segment(line[pos:], base))
        return segments or [Segment(line, base)]


# --------------------------------------------------------------------------
# Modal screens
# --------------------------------------------------------------------------


class InfoScreen(ModalScreen[None]):
    """Details of a single book."""

    BINDINGS = [Binding("escape,q,i", "dismiss", "Close")]

    DEFAULT_CSS = """
    InfoScreen { align: center middle; }
    InfoScreen > VerticalScroll {
        width: 80; max-width: 95%; height: auto; max-height: 90%;
        border: round $primary; background: $surface; padding: 1 2;
    }
    InfoScreen .title { text-style: bold; }
    InfoScreen .hint { color: $text-muted; margin-top: 1; }
    """

    def __init__(self, book: Book, on_shelf: bool) -> None:
        super().__init__()
        self.book = book
        self.on_shelf = on_shelf

    def compose(self) -> ComposeResult:
        b = self.book
        rows = [
            ("Author", b.authors or "—"),
            ("Language", b.language),
            ("Issued", b.issued),
            ("Subjects", b.subjects.replace("; ", "\n") or "—"),
            ("Bookshelves", b.bookshelves.replace("; ", "\n") or "—"),
            ("URL", b.url),
            ("On shelf", "yes" if self.on_shelf else "no"),
        ]
        with VerticalScroll():
            yield Static(b.title, classes="title")
            for name, value in rows:
                yield Static(Text.assemble((f"{name}: ", "bold"), value))
            yield Static("esc to close", classes="hint")


class CatalogScreen(ModalScreen[bool]):
    """Downloads and indexes the catalogue with a progress bar."""

    DEFAULT_CSS = """
    CatalogScreen { align: center middle; }
    CatalogScreen > Vertical {
        width: 60; height: auto; border: round $primary; background: $surface; padding: 1 2;
    }
    CatalogScreen Label { margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Downloading catalogue from gutenberg.org…", id="status")
            yield ProgressBar(total=100, show_eta=False, id="progress")

    def on_mount(self) -> None:
        self.download()

    @work(thread=True, exclusive=True)
    def download(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)

        def progress(done: int, total: int | None) -> None:
            if total:
                app.call_from_thread(self.query_one(ProgressBar).update, progress=100 * done / total)

        try:
            count = app.refresh_catalog(progress, status=lambda s: app.call_from_thread(self.query_one("#status", Label).update, s))
        except Exception as exc:  # network / parse errors
            app.call_from_thread(app.notify, f"Catalogue download failed: {exc}", severity="error", timeout=10)
            app.call_from_thread(self.dismiss, False)
            return
        app.call_from_thread(app.notify, f"Catalogue ready: {count:,} books")
        app.call_from_thread(self.dismiss, True)


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------


class BookActions:
    """Bindings and actions shared by screens that show a BookList."""

    BINDINGS = [
        Binding("enter", "open", "Read"),
        Binding("a", "shelve", "Add to shelf"),
        Binding("i", "info", "Info"),
    ]

    def current_book(self) -> Book | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def action_open(self) -> None:
        book = self.current_book()
        if book:
            self.app.open_book(book)  # type: ignore[attr-defined]

    def action_shelve(self) -> None:
        book = self.current_book()
        if book:
            self.app.add_to_shelf(book)  # type: ignore[attr-defined]

    def action_info(self) -> None:
        book = self.current_book()
        if book:
            self.app.show_info(book)  # type: ignore[attr-defined]


class MainScreen(BookActions, Screen):
    TITLE = "Gutenberg"

    BINDINGS = [
        Binding("slash", "search", "Search"),
        Binding("b", "browse", "Browse"),
        Binding("s", "shelf", "Shelf"),
        Binding("r", "refresh", "Refresh catalogue"),
        Binding("q", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    MainScreen Input { margin: 0 1; }
    MainScreen BookList { height: 1fr; margin: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search title, author, subject… (type to search, ↓ for results)", id="query")
        yield BookList(id="results")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self.refresh_results()

    def current_book(self) -> Book | None:
        return self.query_one(BookList).current

    def refresh_results(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        query = self.query_one(Input).value
        books = app.catalog.search(query)
        self.query_one(BookList).set_books(books)
        self.sub_title = f"{len(books)} results" if query.strip() else f"{app.catalog.count():,} books — newest first"

    @on(Input.Changed)
    def _on_changed(self) -> None:
        self.set_timer(0.15, self.refresh_results, name="search")

    @on(Input.Submitted)
    def _on_submitted(self) -> None:
        self.query_one(BookList).focus()

    def on_key(self, event) -> None:
        if event.key == "down" and self.query_one(Input).has_focus:
            self.query_one(BookList).focus()
            event.stop()
        elif event.key == "escape" and self.query_one(Input).has_focus:
            self.query_one(BookList).focus()
            event.stop()

    @on(OptionList.OptionSelected)
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        self.action_open()

    def action_search(self) -> None:
        inp = self.query_one(Input)
        inp.focus()
        inp.select_all()

    def action_browse(self) -> None:
        self.app.push_screen(BrowseScreen())

    def action_shelf(self) -> None:
        self.app.push_screen(ShelfScreen())

    def action_refresh(self) -> None:
        self.app.push_screen(CatalogScreen(), lambda ok: self.refresh_results())


class BrowseScreen(BookActions, Screen):
    TITLE = "Browse"

    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("t", "toggle_tab", "Bookshelves/Languages"),
        Binding("tab", "focus_next", "Next pane", show=False),
    ]

    DEFAULT_CSS = """
    BrowseScreen OptionList { text-wrap: nowrap; text-overflow: ellipsis; }
    BrowseScreen Horizontal { height: 1fr; }
    BrowseScreen TabbedContent { width: 40; }
    BrowseScreen #categories-shelves, BrowseScreen #categories-langs { height: 1fr; }
    BrowseScreen BookList { width: 1fr; height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with TabbedContent():
                with TabPane("Bookshelves", id="shelves"):
                    yield OptionList(id="categories-shelves")
                with TabPane("Languages", id="langs"):
                    yield OptionList(id="categories-langs")
            yield BookList(id="results")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        shelves = self.query_one("#categories-shelves", OptionList)
        shelves.add_options(
            [Option(Text.assemble(name, (f"  {count:,}", "dim")), id=f"s:{name}") for name, count in app.catalog.bookshelves()]
        )
        langs = self.query_one("#categories-langs", OptionList)
        langs.add_options(
            [Option(Text.assemble(code, (f"  {count:,}", "dim")), id=f"l:{code}") for code, count in app.catalog.languages()]
        )
        shelves.focus()

    def current_book(self) -> Book | None:
        return self.query_one(BookList).current

    @on(OptionList.OptionHighlighted, "#categories-shelves, #categories-langs")
    def _on_category(self, event: OptionList.OptionHighlighted) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        option_id = event.option.id or ""
        kind, _, name = option_id.partition(":")
        books = app.catalog.by_bookshelf(name) if kind == "s" else app.catalog.by_language(name)
        self.query_one(BookList).set_books(books)
        more = "+" if len(books) >= app.catalog.BROWSE_LIMIT else ""
        self.sub_title = f"{name} — {len(books):,}{more} books"

    @on(OptionList.OptionSelected, "#categories-shelves, #categories-langs")
    def _on_category_selected(self, event: OptionList.OptionSelected) -> None:
        self.query_one(BookList).focus()

    @on(OptionList.OptionSelected, "#results")
    def _on_book_selected(self) -> None:
        self.action_open()

    def action_focus_next(self) -> None:
        self.focus_next()

    def action_toggle_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = "langs" if tabs.active == "shelves" else "shelves"
        self.query_one(f"#categories-{tabs.active}", OptionList).focus()


class ShelfScreen(BookActions, Screen):
    TITLE = "My shelf"

    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("d", "delete", "Remove"),
    ]

    DEFAULT_CSS = """
    ShelfScreen BookList { height: 1fr; margin: 0 1; }
    ShelfScreen .empty { padding: 2 4; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield BookList(id="results")
        yield Static("Your shelf is empty. Press a on a book to add it.", classes="empty", id="empty")
        yield Footer()

    def on_mount(self) -> None:
        self.reload()
        self.query_one(BookList).focus()

    def on_screen_resume(self) -> None:
        self.reload()

    def reload(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        entries = app.shelf.list()
        extra = {}
        for entry in entries:
            local = "saved" if paths.book_path(entry.book.id).exists() else "not downloaded"
            extra[entry.book.id] = f"[{local}]" + (f" ¶{entry.position}" if entry.position else "")
        self.query_one(BookList).set_books([e.book for e in entries], extra)
        self.query_one("#empty").display = not entries
        self.sub_title = f"{len(entries)} books"

    def current_book(self) -> Book | None:
        return self.query_one(BookList).current

    @on(OptionList.OptionSelected)
    def _on_selected(self) -> None:
        self.action_open()

    def action_delete(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        book = self.current_book()
        if not book:
            return
        app.shelf.remove(book.id)
        paths.book_path(book.id).unlink(missing_ok=True)
        app.notify(f"Removed “{book.short_title}” from shelf")
        self.reload()


class ReaderScreen(Screen):
    BINDINGS = [
        Binding("escape,q", "back", "Back"),
        Binding("slash", "search", "Search in book"),
        Binding("n", "next_match", "Next", show=False),
        Binding("N", "previous_match", "Previous", show=False),
        Binding("a", "shelve", "Add to shelf"),
        Binding("i", "info", "Info"),
        Binding("j", "line_down", "Down", show=False),
        Binding("k", "line_up", "Up", show=False),
        Binding("space", "page_down", "Page down", show=False),
        Binding("b", "page_up", "Page up", show=False),
        Binding("g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
    ]

    DEFAULT_CSS = """
    ReaderScreen #page { height: 1fr; align-horizontal: center; }
    ReaderScreen #search { display: none; }
    ReaderScreen #search.visible { display: block; }
    ReaderScreen LoadingIndicator { height: 1fr; }
    """

    def __init__(self, book: Book) -> None:
        super().__init__()
        self.book = book
        self.title = book.short_title
        self.loaded = False
        self.view = BookView(id="view")

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="page"):
            yield LoadingIndicator(id="loading")
            yield self.view
        yield Input(placeholder="Search in book… (enter: find, esc: close)", id="search")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(BookView).display = False
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        path = paths.book_path(self.book.id)
        try:
            if not path.exists():
                app.call_from_thread(self._set_subtitle, "downloading…")
                gutenberg.fetch_book(self.book.id, path)
            raw = gutenberg.read_book(path)
        except gutenberg.BookNotAvailable:
            app.call_from_thread(app.notify, f"Book #{self.book.id} has no plain-text edition", severity="error", timeout=8)
            app.call_from_thread(self.app.pop_screen)
            return
        except Exception as exc:
            app.call_from_thread(app.notify, f"Could not load book: {exc}", severity="error", timeout=8)
            app.call_from_thread(self.app.pop_screen)
            return
        paras = text.paragraphs(text.strip_boilerplate(raw))
        app.call_from_thread(self._show, paras)

    def _set_subtitle(self, value: str) -> None:
        self.sub_title = value

    def _show(self, paras: list[str]) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        view = self.query_one(BookView)
        self.query_one(LoadingIndicator).display = False
        view.display = True
        view.set_paragraphs(paras, app.shelf.get_position(self.book.id))
        view.focus()
        self.loaded = True
        self._update_status()
        self.set_interval(2.0, self._save_position)

    def _update_status(self) -> None:
        view = self.query_one(BookView)
        status = f"{view.percent}%"
        if view.needle:
            if view.matches:
                status += f"  match {view.match_index + 1}/{len(view.matches)} for “{view.needle}”"
            else:
                status += f"  no matches for “{view.needle}”"
        self.sub_title = status

    @on(BookView.Scrolled)
    def _on_scrolled(self) -> None:
        self._update_status()

    def _save_position(self) -> None:
        app = self.app
        assert isinstance(app, GutenbergApp)
        if self.loaded and app.shelf.contains(self.book.id):
            app.shelf.set_position(self.book.id, self.view.top_paragraph)

    def on_screen_suspend(self) -> None:
        self._save_position()

    def on_unmount(self) -> None:
        self._save_position()

    # -- actions -----------------------------------------------------------

    def action_back(self) -> None:
        search = self.query_one("#search", Input)
        if search.has_focus:
            self._hide_search()
        else:
            self.app.pop_screen()

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()
        search.select_all()

    def _hide_search(self) -> None:
        self.query_one("#search", Input).remove_class("visible")
        self.query_one(BookView).focus()

    @on(Input.Submitted, "#search")
    def _on_search(self, event: Input.Submitted) -> None:
        view = self.query_one(BookView)
        count = view.set_needle(event.value)
        self._hide_search()
        self._update_status()
        if event.value.strip() and not count:
            self.notify(f"No matches for “{event.value.strip()}”", severity="warning")

    def action_next_match(self) -> None:
        self.query_one(BookView).next_match()
        self._update_status()

    def action_previous_match(self) -> None:
        self.query_one(BookView).previous_match()
        self._update_status()

    def action_shelve(self) -> None:
        self.app.add_to_shelf(self.book)  # type: ignore[attr-defined]
        self._save_position()

    def action_info(self) -> None:
        self.app.show_info(self.book)  # type: ignore[attr-defined]

    def action_line_down(self) -> None:
        self.query_one(BookView).scroll_relative(y=1, animate=False)

    def action_line_up(self) -> None:
        self.query_one(BookView).scroll_relative(y=-1, animate=False)

    def action_page_down(self) -> None:
        self.query_one(BookView).scroll_page_down(animate=False)

    def action_page_up(self) -> None:
        self.query_one(BookView).scroll_page_up(animate=False)

    def action_top(self) -> None:
        self.query_one(BookView).scroll_home(animate=False)

    def action_bottom(self) -> None:
        self.query_one(BookView).scroll_end(animate=False)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------


class GutenbergApp(App[None]):
    TITLE = "Gutenberg"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", show=False, priority=True)]

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.db_path = db_path or paths.db_path()
        self.conn: sqlite3.Connection = connect(self.db_path)
        self.catalog = Catalog(self.conn)
        self.shelf = Shelf(self.conn)

    def on_mount(self) -> None:
        self.push_screen(MainScreen())
        if self.catalog.is_empty():
            self.push_screen(CatalogScreen(), self._after_catalog)
        else:
            updated = self.catalog.updated_at()
            if updated is None or datetime.now(UTC) - updated > CATALOG_MAX_AGE:
                self.background_refresh()

    def _after_catalog(self, ok: bool | None) -> None:
        main = self.screen
        if isinstance(main, MainScreen):
            main.refresh_results()

    # -- catalogue ---------------------------------------------------------

    def refresh_catalog(self, progress=None, status=None) -> int:
        """Download and import the catalogue. Runs in a worker thread."""
        csv_path = paths.data_dir() / "pg_catalog.csv"
        gutenberg.fetch_catalog(csv_path, progress)
        if status:
            status("Indexing catalogue…")
        conn = connect(self.db_path)
        try:
            return Catalog(conn).import_csv(csv_path)
        finally:
            conn.close()

    @work(thread=True, exclusive=True, group="catalog")
    def background_refresh(self) -> None:
        try:
            count = self.refresh_catalog()
        except Exception as exc:
            self.call_from_thread(self.notify, f"Catalogue refresh failed: {exc}", severity="warning", timeout=8)
            return
        self.call_from_thread(self.notify, f"Catalogue refreshed: {count:,} books")
        self.call_from_thread(self._after_catalog, True)

    # -- book actions ------------------------------------------------------

    def open_book(self, book: Book) -> None:
        self.push_screen(ReaderScreen(book))

    def show_info(self, book: Book) -> None:
        self.push_screen(InfoScreen(book, self.shelf.contains(book.id)))

    def add_to_shelf(self, book: Book) -> None:
        if not self.shelf.add(book.id):
            self.notify(f"“{book.short_title}” is already on your shelf")
            return
        self.notify(f"Added “{book.short_title}” to your shelf")
        if not paths.book_path(book.id).exists():
            self.download_for_shelf(book)

    @work(thread=True, group="downloads")
    def download_for_shelf(self, book: Book) -> None:
        try:
            gutenberg.fetch_book(book.id, paths.book_path(book.id))
        except gutenberg.BookNotAvailable:
            self.call_from_thread(self.notify, f"“{book.short_title}” has no plain-text edition; kept on shelf without a file", severity="warning", timeout=8)
        except Exception as exc:
            self.call_from_thread(self.notify, f"Download of “{book.short_title}” failed: {exc}", severity="error", timeout=8)
        else:
            self.call_from_thread(self.notify, f"Saved “{book.short_title}” locally")
