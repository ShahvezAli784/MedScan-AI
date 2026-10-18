from datetime import date, timedelta

import config
from src.safety import checks

TODAY = date(2026, 10, 18)


def item(brand, ingredient, expiry=None, status="active"):
    return {"id": hash(brand) % 1000, "brand_name": brand, "active_ingredient": ingredient,
            "expiry_date": expiry, "status": status}


def test_is_expired():
    assert checks.is_expired("2026-10-17", TODAY)
    assert not checks.is_expired("2026-10-18", TODAY)
    assert not checks.is_expired(None, TODAY)
    assert not checks.is_expired("garbage", TODAY)


def test_expiry_status_boundaries():
    assert checks.expiry_status("2026-10-17", TODAY) == checks.STATUS_EXPIRED
    assert checks.expiry_status(TODAY + timedelta(days=60), TODAY) == checks.STATUS_SOON
    assert checks.expiry_status(TODAY + timedelta(days=61), TODAY) == checks.STATUS_OK
    assert checks.expiry_status(None, TODAY) == checks.STATUS_UNKNOWN


def test_expiring_within_excludes_expired_and_used_up():
    items = [
        item("A", "x", "2026-10-01"),                       # expired
        item("B", "x", "2026-11-10"),                       # soon
        item("C", "x", "2027-06-01"),                       # fine
        item("D", "x", "2026-11-01", status="used_up"),     # used up
        item("E", "x", None),
    ]
    assert [i["brand_name"] for i in checks.expiring_within(items, 60, TODAY)] == ["B"]
    assert [i["brand_name"] for i in checks.expired_items(items, TODAY)] == ["A"]


def test_annotate_items():
    out = checks.annotate_items([item("A", "x", "2026-10-28")], TODAY)
    assert out[0]["expiry_status"] == checks.STATUS_SOON and out[0]["days_left"] == 10


def test_duplicate_message_has_no_dosing_or_verdict():
    group = checks.find_duplicate_ingredients([item("A", "Paracetamol"), item("B", "Paracetamol")])[0]
    assert group.message == config.DUPLICATE_WARNING
    assert "dose" not in group.message.lower() and "safe" not in group.message.lower()
