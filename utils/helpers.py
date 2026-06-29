"""Small, generic helper functions used across handlers."""

import html
import re
from typing import Sequence

CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def is_valid_code(code: str) -> bool:
    """A movie code may be numeric (101) or alphanumeric (S01E02), but must
    be short and free of whitespace/special characters to stay URL/markup safe."""
    return bool(CODE_PATTERN.match(code.strip()))


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def paginate(items: Sequence, page: int, per_page: int) -> Sequence:
    start = page * per_page
    return items[start:start + per_page]


def format_timestamp(ts: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def chunked(iterable: Sequence, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]
