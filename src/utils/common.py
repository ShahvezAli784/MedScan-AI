"""Small shared helpers (dates, text)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional


def parse_iso_date(value: Any) -> Optional[date]:
    """Convert a ``date``/``datetime``/ISO string to a ``date``; return None if impossible."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def format_date(value: Any, fallback: str = "-") -> str:
    """Format a date-like value as ``DD Mon YYYY``."""
    parsed = parse_iso_date(value)
    return parsed.strftime("%d %b %Y") if parsed else fallback


def clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()
