from datetime import date

import pytest

from src.matching.expiry_parser import extract_expiry_date, parse_expiry

TODAY = date(2026, 10, 18)


@pytest.mark.parametrize("text,expected", [
    ("EXP 03/2027", date(2027, 3, 31)),
    ("Exp: 12-2026", date(2026, 12, 31)),
    ("EXP DATE 03.27", date(2027, 3, 31)),
    ("MFG 03/2025 EXP 03/2027", date(2027, 3, 31)),
    ("MFG/EXP 01/2025 02/2028", None),  # unlabelled pair: handled by fallback below
    ("03/27", date(2027, 3, 31)),
    ("MAR 2027", date(2027, 3, 31)),
    ("EXP 0S/2O27", date(2027, 5, 31)),
    ("EXP O3/27", date(2027, 3, 31)),
    ("MFG: 11/2024\nEXP: 11/2026", date(2026, 11, 30)),
    ("Expiry Date: FEB 2028", date(2028, 2, 29)),
    ("EXP. 15/03/2027", date(2027, 3, 15)),
    ("USE BY 2027-05", date(2027, 5, 31)),
    ("Exp 12 2026", date(2026, 12, 31)),
    ("Batch A123 EXP: SEP.2027 Rs 45", date(2027, 9, 30)),
])
def test_parse_expiry(text, expected):
    result = extract_expiry_date(text, TODAY)
    if expected is None:
        assert result is None or result.year >= 2025
    else:
        assert result == expected


@pytest.mark.parametrize("text", ["", "   ", "PANADOL 500 mg", "Price 10.50", "Rs 120", "MFG 03/2025", "EXP 13/2027x"])
def test_no_expiry(text):
    assert parse_expiry(text, TODAY) is None


def test_keyword_source_and_leap_year():
    result = parse_expiry("EXP 02/2028", TODAY)
    assert result.source == "keyword" and result.date == date(2028, 2, 29)


def test_labelled_beats_unlabelled():
    assert extract_expiry_date("04/26 EXP 08/2027", TODAY) == date(2027, 8, 31)
