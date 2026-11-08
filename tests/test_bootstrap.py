from __future__ import annotations

import sqlite3

from getsinapi.bootstrap import _month_shift, database_is_valid


def test_month_shift_crosses_year_boundary():
    assert _month_shift(2026, 1, -1) == (2025, 12)
    assert _month_shift(2026, 12, 1) == (2027, 1)


def test_database_is_valid_requires_integrity_and_reference(tmp_path):
    path = tmp_path / "getsinapi.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE source_references(reference TEXT PRIMARY KEY);
            CREATE TABLE input_prices(reference TEXT);
            CREATE TABLE compositions(reference TEXT);
            CREATE TABLE composition_items(reference TEXT);
            INSERT INTO source_references VALUES ('2026-09');
        """)
    assert database_is_valid(path)


def test_database_is_invalid_when_empty(tmp_path):
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()
    assert not database_is_valid(path)
