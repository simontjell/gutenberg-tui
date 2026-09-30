import pytest

from gutenberg_tui.catalog import Catalog, connect

CSV = '''Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves
1342,Text,1998-06-01,Pride and Prejudice,en,"Austen, Jane, 1775-1817",Courtship -- Fiction; Sisters -- Fiction,PR,"Best Books Ever Listings; Category: Novels"
84,Text,1993-10-01,"Frankenstein; Or, The Modern Prometheus",en,"Shelley, Mary Wollstonecraft, 1797-1851",Horror tales; Science fiction,PR,"Category: Novels; Category: Science-Fiction & Fantasy"
2000,Text,2000-01-01,Don Quijote,es,"Cervantes Saavedra, Miguel de, 1547-1616",Knights and knighthood -- Fiction,PQ,Category: Novels
999,Sound,2005-01-01,Some audiobook,en,Nobody,,,
bad,Text,2005-01-01,Broken row,en,Nobody,,,
'''


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "pg_catalog.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "catalog.db")


@pytest.fixture
def catalog(conn, csv_path):
    cat = Catalog(conn)
    cat.import_csv(csv_path)
    return cat
