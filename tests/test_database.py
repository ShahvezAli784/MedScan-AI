import csv
import re

import pytest

import config
from src.database import db


def test_seed_loaded_once(conn):
    assert len(db.list_medicines(conn)) == 60
    db.init_db(conn)  # second run must not duplicate
    assert len(db.list_medicines(conn)) == 60


def test_seed_content_rules():
    with config.SEED_CSV_PATH.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 60
    assert all(r["source"] == config.SEED_SOURCE for r in rows)
    banned = re.compile(r"\b(dose|doses|dosage|daily|twice|thrice|per day|times a day)\b", re.I)
    assert not [r["brand_name"] for r in rows if banned.search(r["uses"] + " " + r["warnings"])]
    for ingredient in ("Paracetamol", "Ibuprofen"):
        assert sum(r["active_ingredient"] == ingredient for r in rows) >= 2


def test_demo_user_exists_with_sample_cabinet(conn):
    demo = db.get_user_by_email(conn, config.DEMO_EMAIL)
    assert demo and "password_hash" not in demo
    assert len(db.list_cabinet(conn, demo["id"])) == 5


def test_password_hashing_and_auth(conn):
    uid = db.create_user(conn, "Ayesha", "Ayesha@Example.com", "correct horse", "Urdu")
    stored = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert "correct horse" not in stored and stored.startswith("pbkdf2_sha256$")
    assert db.authenticate(conn, "ayesha@example.com", "correct horse")["id"] == uid
    assert db.authenticate(conn, "ayesha@example.com", "wrong password") is None
    assert db.authenticate(conn, "nobody@example.com", "x" * 10) is None


@pytest.mark.parametrize("name,email,pw", [
    ("", "a@b.com", "longenough"), ("A", "not-an-email", "longenough"), ("A", "a@b.com", "short")])
def test_registration_validation(conn, name, email, pw):
    with pytest.raises(ValueError):
        db.create_user(conn, name, email, pw)


def test_duplicate_email_rejected(conn):
    db.create_user(conn, "A", "a@b.com", "longenough")
    with pytest.raises(ValueError):
        db.create_user(conn, "B", "A@B.com", "longenough")


def test_cabinet_crud_and_user_isolation(conn):
    u1 = db.create_user(conn, "U1", "u1@x.com", "longenough")
    u2 = db.create_user(conn, "U2", "u2@x.com", "longenough")
    med = db.get_medicine_by_brand(conn, "panadol")
    cid = db.add_cabinet_item(conn, u1, med["id"], "PANADOL", 97.5, "2027-03-31")
    row = db.list_cabinet(conn, u1)[0]
    assert row["brand_name"] == "Panadol" and row["status"] == "active" and row["match_confidence"] == 97.5
    assert db.list_cabinet(conn, u2) == []
    assert not db.set_cabinet_status(conn, u2, cid, "used_up")      # other user cannot modify
    assert not db.delete_cabinet_item(conn, u2, cid)
    assert db.set_cabinet_status(conn, u1, cid, "used_up")
    assert db.list_cabinet(conn, u1, "active") == [] and len(db.list_cabinet(conn, u1, "used_up")) == 1
    assert db.delete_cabinet_item(conn, u1, cid) and db.list_cabinet(conn, u1) == []


def test_invalid_inputs(conn):
    with pytest.raises(ValueError):
        db.add_cabinet_item(conn, 1, 99999, "x", 1.0, None)
    with pytest.raises(ValueError):
        db.set_cabinet_status(conn, 1, 1, "bogus")


def test_update_profile(conn):
    uid = db.create_user(conn, "A", "a@b.com", "longenough")
    db.update_user_profile(conn, uid, "New Name", "Roman Urdu")
    assert db.get_user(conn, uid)["language_pref"] == "Roman Urdu"
    with pytest.raises(ValueError):
        db.update_user_profile(conn, uid, "X", "Klingon")
