from gutenberg_tui.text import find, paragraphs, strip_boilerplate, wrap

RAW = """The Project Gutenberg eBook of Foo
Title: Foo

*** START OF THE PROJECT GUTENBERG EBOOK FOO ***

CHAPTER I

It is a truth universally acknowledged, that a single man in
possession of a good fortune, must be in want of a wife.

    Roses are red,
    Violets are blue.

*** END OF THE PROJECT GUTENBERG EBOOK FOO ***

Licence blah.
"""


def test_strip_boilerplate_cuts_header_and_footer():
    body = strip_boilerplate(RAW)
    assert body.startswith("CHAPTER I")
    assert body.rstrip().endswith("Violets are blue.")
    assert "Licence" not in body


def test_strip_boilerplate_without_markers_is_identity():
    assert strip_boilerplate("just text\n") == "just text"


def test_paragraphs_joins_prose_and_keeps_verse():
    paras = paragraphs(strip_boilerplate(RAW))
    assert paras[0] == "CHAPTER I"
    assert paras[1].startswith("It is a truth") and "\n" not in paras[1]
    assert paras[2] == "    Roses are red,\n    Violets are blue."


def test_paragraphs_handles_crlf():
    assert paragraphs("a\r\nb\r\n\r\nc") == ["a b", "c"]


def test_wrap_tracks_paragraph_index_and_separators():
    lines = wrap(["one two three four five", "six"], 10)
    assert lines == [(0, "one two"), (0, "three four"), (0, "five"), (0, ""), (1, "six")]


def test_wrap_keeps_verse_lines():
    lines = wrap(["  a\n  b"], 40)
    assert lines == [(0, "  a"), (0, "  b")]


def test_find_is_case_insensitive():
    assert find(["Hello World", "nothing", "world peace"], "WORLD") == [0, 2]
    assert find(["x"], "  ") == []
