from __future__ import annotations

import sqlite3
from datetime import date

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



def test_reference_discovery_retries_http_429_then_succeeds(tmp_path, monkeypatch):
    from getsinapi import bootstrap
    from getsinapi.config import Settings

    settings = Settings(
        environment="test", log_level="INFO",
        data_dir=tmp_path, raw_dir=tmp_path / "raw",
        staging_dir=tmp_path / "staging", processed_dir=tmp_path / "processed",
        manifest_dir=tmp_path / "manifests", http_timeout=2,
        http_max_retries=2, http_backoff_seconds=0,
    )
    statuses = [429, 200]
    calls = []

    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.headers = {"Retry-After": "0"}
            self.closed = False

        def close(self):
            self.closed = True

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(statuses.pop(0))

    monkeypatch.setattr(bootstrap.requests, "get", fake_get)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda seconds: None)

    assert bootstrap._reference_exists("2026-11", settings) is True
    assert len(calls) == 2


def test_reference_discovery_stops_after_retry_limit_on_429(tmp_path, monkeypatch):
    import pytest
    from getsinapi import bootstrap
    from getsinapi.collectors.caixa import CaixaDownloadError
    from getsinapi.config import Settings

    settings = Settings(
        environment="test", log_level="INFO",
        data_dir=tmp_path, raw_dir=tmp_path / "raw",
        staging_dir=tmp_path / "staging", processed_dir=tmp_path / "processed",
        manifest_dir=tmp_path / "manifests", http_timeout=2,
        http_max_retries=1, http_backoff_seconds=0,
    )

    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "0"}

        def close(self):
            pass

    calls = []
    monkeypatch.setattr(bootstrap.requests, "get", lambda *a, **k: calls.append(1) or FakeResponse())
    monkeypatch.setattr(bootstrap.time, "sleep", lambda seconds: None)

    with pytest.raises(CaixaDownloadError, match="após 1 tentativas"):
        bootstrap._reference_exists("2026-11", settings)
    assert len(calls) == 2
