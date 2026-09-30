import pytest

from gutenberg_tui import paths
from gutenberg_tui.app import BookList, BookView, GutenbergApp, MainScreen, ReaderScreen, ShelfScreen
from gutenberg_tui.text import strip_boilerplate

BOOK = """*** START OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***

Letter 1

You will rejoice to hear that no disaster has accompanied the
commencement of an enterprise which you have regarded with such evil
forebodings.

""" + "\n\n".join(f"Paragraph number {i} of filler text so that the book scrolls." for i in range(200)) + """

The needle is in this haystack paragraph.

*** END OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***
"""


@pytest.fixture
def app(catalog, tmp_path, monkeypatch):
    monkeypatch.setenv("GUTENBERG_TUI_DATA", str(tmp_path))
    paths.book_path(84).write_text(BOOK, encoding="utf-8")
    return GutenbergApp(db_path=tmp_path / "catalog.db")


async def test_search_lists_results(app):
    async with app.run_test(size=(100, 30)) as pilot:
        assert isinstance(app.screen, MainScreen)
        await pilot.press(*"frank")
        await pilot.pause(0.3)
        results = app.screen.query_one(BookList)
        assert [b.id for b in results.books] == [84]
        assert results.current is not None and results.current.id == 84


async def test_open_reader_search_and_shelf(app):
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press(*"frank")
        await pilot.pause(0.3)
        await pilot.press("enter")  # focus results
        await pilot.press("enter")  # open reader
        await pilot.pause(0.5)
        assert isinstance(app.screen, ReaderScreen)
        view = app.screen.query_one(BookView)
        assert view.paras[0] == "Letter 1"
        assert "Letter 1" in view.render_line(0).text

        # search inside the book
        await pilot.press("slash")
        await pilot.press(*"haystack")
        await pilot.press("enter")
        await pilot.pause()
        assert view.matches == [view.paras.index("The needle is in this haystack paragraph.")]
        assert "match 1/1" in app.screen.sub_title
        visible = [view.render_line(y).text for y in range(view.size.height)]
        assert any("haystack" in line for line in visible)

        # add to shelf and remember position
        await pilot.press("a")
        await pilot.pause()
        assert app.shelf.contains(84)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        assert app.shelf.get_position(84) == view.top_paragraph > 0

        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, ShelfScreen)
        assert [b.id for b in app.screen.query_one(BookList).books] == [84]
        await pilot.press("enter")
        await pilot.pause(0.5)
        assert isinstance(app.screen, ReaderScreen)
        assert app.screen.query_one(BookView).top_paragraph == app.shelf.get_position(84)
