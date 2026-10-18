"""Pytest setup: make the project root importable and provide shared fixtures."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import db  # noqa: E402


@pytest.fixture()
def conn():
    """Fresh in-memory database, schema created, seeded, demo user present."""
    connection = db.connect(":memory:")
    db.init_db(connection)
    yield connection
    connection.close()


@pytest.fixture()
def medicines(conn):
    """All seeded medicines."""
    return db.list_medicines(conn)
