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



def test_bootstrap_coalesces_concurrent_runs(monkeypatch):
    from getsinapi import bootstrap

    assert bootstrap._BOOTSTRAP_LOCK.acquire(blocking=False)
    try:
        result = bootstrap.run_bootstrap()
        assert result["status"] == "already_running"
    finally:
        bootstrap._BOOTSTRAP_LOCK.release()

def test_catalog_cache_requires_complete_monthly_history():
    from getsinapi.bootstrap import _catalog_has_full_monthly_range

    assert _catalog_has_full_monthly_range({
        "2025-01": "https://caixa.gov.br/2025-01.zip",
        "2025-02": "https://caixa.gov.br/2025-02.zip",
        "2025-03": "https://caixa.gov.br/2025-03.zip",
    })
    assert not _catalog_has_full_monthly_range({
        "2026-09": "https://caixa.gov.br/2026-09.zip",
    })
    assert not _catalog_has_full_monthly_range({
        "2025-01": "https://caixa.gov.br/2025-01.zip",
        "2025-03": "https://caixa.gov.br/2025-03.zip",
    })
