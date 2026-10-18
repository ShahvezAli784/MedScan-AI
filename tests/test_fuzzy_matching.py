import pytest

import config
from src.matching.fuzzy_match import build_candidates, match_medicine, normalize_text, search_medicines


@pytest.mark.parametrize("text,expected", [
    ("PANADOL 500mg", "Panadol"),
    ("PANAD0L", "Panadol"),
    ("Panadol Extra Paracetamol 500mg Caffeine 65mg", "Panadol Extra"),
    ("BRUFEN 4OO mg film coated", "Brufen"),
    ("Ponstan Forte Mefenamic acid", "Ponstan"),
    ("AUGMENTIN 625 amoxicillin clavulanic", "Augmentin"),
    ("Surbex-Z", "Surbex-Z"),
    ("CAC 1000 Plus", "Cac-1000 Plus"),
    ("Zyrtec 10mg", "Zyrtec"),
    ("nexium 40", "Nexium"),
    ("FLAGYL 400", "Flagyl"),
    ("ORS", "ORS Sachet"),
])
def test_top_match(medicines, text, expected):
    matches = match_medicine(text, medicines)
    assert matches and matches[0].brand_name == expected and matches[0].meets_threshold


@pytest.mark.parametrize("text", ["xyzzy lorem ipsum", "BATCH 1234 MFG 2024", "", "   ", "!!!"])
def test_garbage_is_below_threshold(medicines, text):
    matches = match_medicine(text, medicines)
    assert not any(m.meets_threshold for m in matches)


def test_returns_at_most_three_sorted(medicines):
    matches = match_medicine("paracetamol tablets", medicines)
    assert len(matches) <= config.TOP_K_MATCHES
    assert [m.score for m in matches] == sorted((m.score for m in matches), reverse=True)


def test_multiline_input(medicines):
    assert match_medicine(["Tablets", "PANADOL", "Exp 03/2027"], medicines)[0].brand_name == "Panadol"


def test_normalize_and_candidates():
    assert normalize_text("PANAD0L-500") == "panadol 500"
    cands = build_candidates("Panadol Extra 500mg")
    assert "panadol extra" in cands and "panadol" in cands


def test_manual_search(medicines):
    assert search_medicines("panad", medicines)[0]["brand_name"].startswith("Panadol")
    assert any(m["brand_name"] == "Brufen" for m in search_medicines("ibuprofen", medicines))
    assert search_medicines("", medicines) == []
