import time

from gutenberg_tui.catalog import Catalog, connect


def test_short_prefix_search_is_fast_on_large_catalog(tmp_path):
    """A one-letter query matches most rows; ranking must not be per-row."""
    path = tmp_path / "big.csv"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n")
        for i in range(20000):
            handle.write(f'{i},Text,2000-01-01,"Harbour history {i}",en,"Hansen, Hans",History,D,"Category: History"\n')
    cat = Catalog(connect(tmp_path / "big.db"))
    cat.import_csv(path)
    start = time.perf_counter()
    results = cat.search("h")
    assert time.perf_counter() - start < 1.0
    assert len(results) == 200
