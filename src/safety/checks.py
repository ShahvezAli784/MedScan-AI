"""Deterministic safety checks: expiry status and duplicate active ingredients."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Optional

import config
from src.utils.common import parse_iso_date

Item = dict[str, Any]

STATUS_OK = "ok"
STATUS_SOON = "expiring_soon"
STATUS_EXPIRED = "expired"
STATUS_UNKNOWN = "unknown"

_SALT_WORDS = {
    "sodium", "potassium", "hydrochloride", "hcl", "maleate", "besilate", "besylate",
    "trihydrate", "monohydrate", "dihydrate", "hydrobromide", "sulfate", "sulphate",
}


def days_until_expiry(expiry: Any, today: Optional[date] = None) -> Optional[int]:
    """Days from ``today`` until ``expiry`` (negative if already expired); None if unknown."""
    parsed = parse_iso_date(expiry)
    if parsed is None:
        return None
    return (parsed - (today or date.today())).days


def is_expired(expiry: Any, today: Optional[date] = None) -> bool:
    """True if the expiry date is before today. Unknown dates are never reported as expired."""
    days = days_until_expiry(expiry, today)
    return days is not None and days < 0


def expiry_status(
    expiry: Any, today: Optional[date] = None, soon_days: int = config.EXPIRY_SOON_DAYS
) -> str:
    """Classify an expiry date as ok / expiring_soon / expired / unknown."""
    days = days_until_expiry(expiry, today)
    if days is None:
        return STATUS_UNKNOWN
    if days < 0:
        return STATUS_EXPIRED
    if days <= soon_days:
        return STATUS_SOON
    return STATUS_OK


def _active(items: Iterable[Item]) -> list[Item]:
    return [i for i in items if i.get("status", config.STATUS_ACTIVE) == config.STATUS_ACTIVE]


def annotate_items(items: Iterable[Item], today: Optional[date] = None) -> list[Item]:
    """Return copies of cabinet items with ``expiry_status`` and ``days_left`` added."""
    out = []
    for item in items:
        copy = dict(item)
        copy["expiry_status"] = expiry_status(item.get("expiry_date"), today)
        copy["days_left"] = days_until_expiry(item.get("expiry_date"), today)
        out.append(copy)
    return out


def expired_items(items: Iterable[Item], today: Optional[date] = None) -> list[Item]:
    """Active items whose expiry date has passed (oldest expiry first)."""
    found = [i for i in _active(items) if is_expired(i.get("expiry_date"), today)]
    return sorted(found, key=lambda i: str(i.get("expiry_date")))


def expiring_within(
    items: Iterable[Item], days: int = config.EXPIRY_SOON_DAYS, today: Optional[date] = None
) -> list[Item]:
    """Active, not-yet-expired items expiring within ``days`` days (soonest first)."""
    today = today or date.today()
    limit = today + timedelta(days=days)
    found = []
    for item in _active(items):
        expiry = parse_iso_date(item.get("expiry_date"))
        if expiry is not None and today <= expiry <= limit:
            found.append(item)
    return sorted(found, key=lambda i: str(i.get("expiry_date")))


# --------------------------------------------------------------------------
# Duplicate active ingredients
# --------------------------------------------------------------------------
def normalize_ingredient(name: str) -> str:
    """Lower-case an ingredient, drop parentheses and salt words (e.g. 'Cetirizine HCl' -> 'cetirizine')."""
    text = re.sub(r"\(.*?\)", " ", name.lower())
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in _SALT_WORDS]
    return " ".join(words)


def split_ingredients(active_ingredient: str) -> list[str]:
    """Split a combination product's active ingredients ('A + B') into normalized parts."""
    parts = re.split(r"\s*(?:\+|,|;|/)\s*", active_ingredient or "")
    return [n for n in (normalize_ingredient(p) for p in parts) if n]


@dataclass
class DuplicateGroup:
    """A shared active ingredient and the active cabinet items that contain it."""

    ingredient: str
    items: list[Item] = field(default_factory=list)

    @property
    def brands(self) -> list[str]:
        """Brand names involved in this group."""
        return [str(i.get("brand_name", "?")) for i in self.items]

    @property
    def message(self) -> str:
        """Neutral wording; deliberately gives no dosing or safety verdict."""
        return config.DUPLICATE_WARNING


def find_duplicate_ingredients(cabinet: Iterable[Item]) -> list[DuplicateGroup]:
    """Group active cabinet items sharing at least one active ingredient (2+ items per group)."""
    groups: dict[str, list[Item]] = {}
    for item in _active(cabinet):
        for ingredient in set(split_ingredients(str(item.get("active_ingredient", "")))):
            groups.setdefault(ingredient, []).append(item)
    return [
        DuplicateGroup(ingredient=ing, items=items)
        for ing, items in sorted(groups.items())
        if len(items) >= 2
    ]
