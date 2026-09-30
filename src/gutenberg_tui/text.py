"""Pure text processing for Gutenberg plain-text books."""

from __future__ import annotations

import re
import textwrap

_START = re.compile(r"^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.M)
_END = re.compile(r"^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.M)


def strip_boilerplate(raw: str) -> str:
    """Remove the Gutenberg licence header and footer if the markers exist."""
    text = raw
    start = _START.search(text)
    if start:
        text = text[start.end():]
    end = _END.search(text)
    if end:
        text = text[: end.start()]
    return text.strip("\n")


def paragraphs(text: str) -> list[str]:
    """Split text into paragraphs.

    Prose paragraphs have their lines joined with single spaces. Paragraphs
    where every line is indented (verse, tables, preformatted blocks) are kept
    line for line.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result: list[str] = []
    for block in re.split(r"\n[ \t]*\n+", text):
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if all(line[0].isspace() for line in lines):
            result.append("\n".join(lines))
        else:
            result.append(" ".join(line.strip() for line in lines))
    return result


def wrap(paras: list[str], width: int) -> list[tuple[int, str]]:
    """Wrap paragraphs to ``width`` columns.

    Returns ``(paragraph_index, line)`` pairs. Paragraphs are separated by an
    empty line attributed to the preceding paragraph.
    """
    width = max(width, 10)
    out: list[tuple[int, str]] = []
    for index, para in enumerate(paras):
        if "\n" in para:
            lines = [line.expandtabs() for line in para.split("\n")]
            for line in lines:
                if len(line) <= width:
                    out.append((index, line))
                else:
                    out.extend((index, chunk) for chunk in textwrap.wrap(line, width) or [""])
        else:
            out.extend((index, line) for line in textwrap.wrap(para, width) or [""])
        out.append((index, ""))
    if out:
        out.pop()  # no trailing separator
    return out


def find(paras: list[str], needle: str) -> list[int]:
    """Indices of paragraphs containing ``needle`` (case-insensitive)."""
    needle = needle.strip().lower()
    if not needle:
        return []
    return [i for i, para in enumerate(paras) if needle in para.lower()]
