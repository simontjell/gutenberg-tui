"""Gutenberg TUI: browse, search and read Project Gutenberg books in the terminal."""


def main() -> None:
    from gutenberg_tui.app import GutenbergApp

    GutenbergApp().run()
