from gutenberg_tui.catalog import Catalog


def test_import_skips_non_text_and_bad_rows(conn, csv_path):
    cat = Catalog(conn)
    assert cat.is_empty()
    assert cat.import_csv(csv_path) == 3
    assert cat.count() == 3
    assert cat.updated_at() is not None


def test_search_by_prefix_on_title_and_author(catalog):
    assert [b.id for b in catalog.search("prid prej")] == [1342]
    assert [b.id for b in catalog.search("shelley")] == [84]
    assert [b.id for b in catalog.search("cervantes")] == [2000]
    assert catalog.search("zzzz") == []


def test_search_ignores_diacritics(catalog):
    assert [b.id for b in catalog.search("quijote")] == [2000]


def test_empty_query_returns_recent(catalog):
    assert [b.id for b in catalog.search("")] == [2000, 1342, 84]


def test_bookshelves_and_languages(catalog):
    assert catalog.bookshelves() == [
        ("Best Books Ever Listings", 1),
        ("Category: Novels", 3),
        ("Category: Science-Fiction & Fantasy", 1),
    ]
    assert catalog.languages() == [("en", 2), ("es", 1)]


def test_by_bookshelf_and_language(catalog):
    assert [b.id for b in catalog.by_bookshelf("Category: Novels")] == [2000, 84, 1342]
    assert [b.id for b in catalog.by_bookshelf("Best Books Ever Listings")] == [1342]
    assert [b.id for b in catalog.by_language("es")] == [2000]


def test_get_and_label(catalog):
    book = catalog.get(84)
    assert book is not None
    assert book.label() == "Frankenstein; Or, The Modern Prometheus — Shelley, Mary Wollstonecraft, 1797-1851"
    assert book.url == "https://www.gutenberg.org/ebooks/84"
    assert catalog.get(1) is None
