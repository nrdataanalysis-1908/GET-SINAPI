from pathlib import Path

import pytest

from getsinapi.config import Settings


def test_settings_defaults(monkeypatch):
    keys = (
        "GETSINAPI_ENV", "GETSINAPI_LOG_LEVEL", "GETSINAPI_DATA_DIR",
        "GETSINAPI_RAW_DIR", "GETSINAPI_STAGING_DIR",
        "GETSINAPI_PROCESSED_DIR", "GETSINAPI_MANIFEST_DIR",
        "GETSINAPI_HTTP_TIMEOUT", "GETSINAPI_HTTP_MAX_RETRIES",
        "GETSINAPI_HTTP_BACKOFF_SECONDS",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env()
    assert settings.environment == "development"
    assert settings.raw_dir == Path("data/raw")
    assert settings.http_timeout == 45
    assert settings.http_max_retries == 4


def test_invalid_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("GETSINAPI_ENV", "staging")
    with pytest.raises(ValueError, match="GETSINAPI_ENV"):
        Settings.from_env()


def test_negative_retry_count_is_rejected(monkeypatch):
    monkeypatch.setenv("GETSINAPI_HTTP_MAX_RETRIES", "-1")
    with pytest.raises(ValueError, match="não pode ser negativo"):
        Settings.from_env()
