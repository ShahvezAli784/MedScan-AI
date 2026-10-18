"""Extract an expiry date from noisy OCR text (EXP 03/2027, Exp: 12-2026, MAR 2027, 03.27 ...)."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

# Characters OCR commonly confuses with digits.
_FIX = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "S": "5", "B": "8", "Z": "2"}
_C = r"[0-9OQDIL|SBZ]"  # "digit-like" character (case-insensitive via re.I)

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}

_KEYWORD = re.compile(
    r"(?<![A-Z])(?:EXP(?:IRY|IRES)?|E\.?X\.?P|USE\s*BY|BEST\s*BEFORE)\b\.?\s*(?:DATE)?\s*[:.\-]?\s*", re.I)
_MFG = re.compile(r"(?:MFG|MFD|MANUF\w*|PROD\w*)\.?\s*(?:DATE)?\s*[:.\-]?\s*$", re.I)

_NAMED = re.compile(
    rf"(?<![A-Z])(?P<mon>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT?|OCT|NOV|DEC)[A-Z]{{0,6}}\.?\s*"
    rf"[/\-.,]?\s*(?P<y>{_C}{{4}}|{_C}{{2}})(?![0-9])", re.I)
_YM = re.compile(r"(?<![0-9])(?P<y>20\d{2})\s*[/\-.]\s*(?P<m>0?[1-9]|1[0-2])(?![0-9])")


def _num_re(sep: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![0-9A-Z])(?:(?P<d>[0-3]?\d)\s*[/\-.]\s*)?(?P<m>[01OQDIL|]?{_C})\s*{sep}\s*"
        rf"(?P<y>{_C}{{4}}|{_C}{{2}})(?![0-9])", re.I)


_NUM_STRICT = _num_re(r"[/\-.]")
_NUM_LOOSE = _num_re(r"[/\-.\s]")


@dataclass(frozen=True)
class ExpiryResult:
    """A parsed expiry date plus the text that produced it."""

    date: date
    raw: str
    source: str  # "keyword" (found after an EXP label) or "fallback" (bare date pattern)


def _to_int(chars: str) -> Optional[int]:
    """Map OCR look-alike characters to digits; None if no real digit is present."""
    if not any(c.isdigit() for c in chars):
        return None
    return int("".join(_FIX.get(c.upper(), c) for c in chars))


def _year(chars: str) -> Optional[int]:
    value = _to_int(chars)
    if value is None:
        return None
    if len(chars) == 2:
        value += 2000
    return value if 2000 <= value <= 2099 else None


def _build(month: Optional[int], year: Optional[int], day: Optional[int] = None) -> Optional[date]:
    """Build a date: the stated day if valid, otherwise the last day of the month."""
    if month is None or year is None or not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    return date(year, month, day if day and 1 <= day <= last else last)


def _match_core(text: str, pos: int, loose: bool) -> Optional[tuple[date, int, str]]:
    """Try to read a date starting exactly at ``pos``; returns (date, end, raw) or None."""
    named = _NAMED.match(text, pos)
    if named:
        found = _build(_MONTHS[named["mon"][:3].upper()], _year(named["y"]))
        if found:
            return found, named.end(), named.group(0)
    ym = _YM.match(text, pos)
    if ym:
        found = _build(int(ym["m"]), int(ym["y"]))
        if found:
            return found, ym.end(), ym.group(0)
    num = (_NUM_LOOSE if loose else _NUM_STRICT).match(text, pos)
    if num:
        day = _to_int(num["d"]) if num["d"] else None
        found = _build(_to_int(num["m"]), _year(num["y"]), day)
        if found:
            return found, num.end(), num.group(0)
    return None


def _fallback_candidates(text: str) -> list[tuple[int, date, str]]:
    """Scan the whole text for bare date patterns, skipping ones labelled MFG/MFD."""
    cands: list[tuple[int, date, str]] = []
    for regex in (_NAMED, _YM, _NUM_STRICT):
        for m in regex.finditer(text):
            if _MFG.search(text[max(0, m.start() - 14): m.start()]):
                continue
            hit = _match_core(text, m.start(), loose=False)
            if hit:
                cands.append((m.start(), hit[0], hit[2]))
    return cands


def parse_expiry(text: str, today: Optional[date] = None) -> Optional[ExpiryResult]:
    """Return the most plausible expiry date in ``text`` (last day of month), or None.

    Labelled dates (``EXP ...``) win; the last one is used so ``MFG .. EXP ..`` lines work.
    Without a label, the latest plausible bare date is used, ignoring MFG-labelled dates and
    years far outside today's range to avoid false positives such as prices.
    """
    if not text or not text.strip():
        return None
    today = today or date.today()
    flat = re.sub(r"[ \t]+", " ", text.replace("\n", " \n "))
    labelled: list[ExpiryResult] = []
    for kw in _KEYWORD.finditer(flat):
        hit = _match_core(flat, kw.end(), loose=True)
        if hit:
            labelled.append(ExpiryResult(hit[0], hit[2].strip(), "keyword"))
    if labelled:
        return labelled[-1]
    plausible = [
        (d, raw) for _, d, raw in _fallback_candidates(flat)
        if today.year - 2 <= d.year <= today.year + 8
    ]
    if not plausible:
        return None
    best, raw = max(plausible, key=lambda c: c[0])
    return ExpiryResult(best, raw.strip(), "fallback")


def extract_expiry_date(text: str, today: Optional[date] = None) -> Optional[date]:
    """Convenience wrapper returning just the date."""
    result = parse_expiry(text, today)
    return result.date if result else None
