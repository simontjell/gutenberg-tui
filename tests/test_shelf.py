from gutenberg_tui.shelf import Shelf


def test_add_list_remove(catalog):
    shelf = Shelf(catalog.conn)
    assert shelf.list() == []
    assert shelf.add(1342) is True
    assert shelf.add(1342) is False
    assert shelf.contains(1342)
    entries = shelf.list()
    assert [e.book.id for e in entries] == [1342]
    assert entries[0].position == 0
    shelf.remove(1342)
    assert not shelf.contains(1342)
    assert shelf.list() == []


def test_position(catalog):
    shelf = Shelf(catalog.conn)
    assert shelf.get_position(84) == 0
    shelf.add(84)
    shelf.set_position(84, 17)
    assert shelf.get_position(84) == 17
    assert shelf.list()[0].position == 17
