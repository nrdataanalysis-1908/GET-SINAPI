import pytest

from getsinapi.config import Settings


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_settings_reject_non_finite_http_backoff(monkeypatch, value):
    monkeypatch.setenv("GETSINAPI_HTTP_BACKOFF_SECONDS", value)

    with pytest.raises(ValueError, match="finito"):
        Settings.from_env()
