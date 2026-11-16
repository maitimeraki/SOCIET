"""Fence helpers: user and graph text enters a prompt only as data inside tags.

Shared by every prompt that wraps untrusted text. Attribute values lose markup
characters and line breaks; bodies lose angle brackets so they cannot close
their own tag.
"""

import re

#: Characters of any one attribute value (names, aliases, titles, types, ids) in a prompt.
ATTR_MAX_CHARS = 120

_MARKUP = re.compile(r'[<>"]')


def attr_text(value: object, limit: int = ATTR_MAX_CHARS) -> str:
    """Attribute or free-text value as data: no markup characters, one line, at most `limit` characters."""
    return " ".join(_MARKUP.sub("", str(value)).split())[:limit]


def body_text(value: str) -> str:
    """Fenced body as data: angle brackets removed so it cannot close the fence."""
    return value.replace("<", "").replace(">", "")
