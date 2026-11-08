import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests

from getsinapi.collectors.caixa import (
    CaixaDownloadError,
    discover_latest_monthly_xlsx,
    download_monthly_xlsx,
    report_url,
    safe_extract_zip,
)
from getsinapi.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        staging_dir=tmp_path / "data" / "staging",
        processed_dir=tmp_path / "data" / "processed",
        manifest_dir=tmp_path / "data" / "manifests",
        http_timeout=2,
        http_max_retries=0,
        http_backoff_seconds=0,
    )


def make_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SINAPI/Referência.xlsx", b"fake-xlsx-content")
    return buffer.getvalue()


def test_report_url_requires_valid_reference():
    assert report_url("2026-09").endswith("SINAPI-2026-09-formato-xlsx.zip")
    with pytest.raises(ValueError):
        report_url("2026-13")


def test_download_saves_zip_and_manifest(tmp_path):
    response = requests.Response()
    response.status_code = 200
    response._content = make_zip()

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    artifact = download_monthly_xlsx(
        "2026-09", settings=make_settings(tmp_path), session=FakeSession()
    )
    assert artifact.path.exists()
    assert artifact.size_bytes > 0
    assert len(artifact.sha256) == 64
    assert list((tmp_path / "data" / "manifests").glob("*.json"))


def test_download_rejects_html_response(tmp_path):
    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>not a zip</html>"

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    with pytest.raises(CaixaDownloadError, match="ZIP válido"):
        download_monthly_xlsx(
            "2026-09", settings=make_settings(tmp_path), session=FakeSession()
        )


def test_safe_extract_blocks_zip_slip(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "malicious")

    with pytest.raises(CaixaDownloadError, match="Caminho inseguro"):
        safe_extract_zip(archive_path, tmp_path / "out")


def test_discovery_uses_official_catalog_and_selects_latest_xlsx(tmp_path):
    from getsinapi.collectors import caixa

    html = """
    <html><body>
      <a href="/Downloads/sinapi-relatorios-mensais/SINAPI-2026-09-formato-xlsx.zip">
        SINAPI-2026-09-formato-xlsx
      </a>
      <a href="/Downloads/sinapi-relatorios-mensais/SINAPI-2026-10-formato-xlsx.zip">
        SINAPI-2026-10-formato-xlsx
      </a>
      <a href="/Downloads/sinapi-relatorios-mensais/SINAPI-2026-11-formato-pdf.zip">
        SINAPI-2026-11-formato-pdf
      </a>
    </body></html>
    """

    class FakeResponse:
        status_code = 200
        text = html

        def close(self):
            pass

    class FakeSession:
        def get(self, url, **kwargs):
            assert url == caixa.DOWNLOADS_PAGE_URL
            return FakeResponse()

    reference, url = discover_latest_monthly_xlsx(
        settings=make_settings(tmp_path), session=FakeSession()
    )
    assert reference == "2026-10"
    assert url.endswith("SINAPI-2026-10-formato-xlsx.zip")


def test_discovery_fails_clearly_when_catalog_is_forbidden(tmp_path):
    class FakeResponse:
        status_code = 403

        def close(self):
            pass

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(CaixaDownloadError, match=r"(?i)índice SharePoint oficial.*HTTP 403"):
        discover_latest_monthly_xlsx(
            settings=make_settings(tmp_path), session=FakeSession()
        )


def test_discovery_uses_sharepoint_when_html_catalog_is_forbidden(tmp_path, monkeypatch):
    from getsinapi.collectors import caixa

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = ""

        def json(self):
            return self._payload

        def close(self):
            pass

    responses = [
        FakeResponse(403),
        FakeResponse(200, {
            "d": {
                "results": [{
                    "FileLeafRef": "SINAPI-2026-10-formato-xlsx.zip",
                    "EncodedAbsUrl": (
                        "https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/"
                        "SINAPI-2026-10-formato-xlsx.zip"
                    ),
                }]
            }
        }),
    ]

    def fake_get(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(caixa, "_http_get", fake_get)
    reference, url = discover_latest_monthly_xlsx(settings=make_settings(tmp_path))
    assert reference == "2026-10"
    assert url.endswith("SINAPI-2026-10-formato-xlsx.zip")


def test_discovery_falls_back_to_sharepoint_when_html_has_no_trusted_xlsx(
    tmp_path, monkeypatch
):
    from getsinapi.collectors import caixa

    class FakeResponse:
        status_code = 200
        text = '<a href="https://evil.example/SINAPI-2026-10-formato-xlsx.zip">XLSX</a>'

        def close(self):
            pass

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    fallback_calls = []

    def fake_sharepoint(settings, session=None):
        fallback_calls.append((settings, session))
        return (
            "2026-10",
            "https://www.caixa.gov.br/Downloads/SINAPI-2026-10-formato-xlsx.zip",
        )

    monkeypatch.setattr(caixa, "_discover_via_sharepoint", fake_sharepoint)
    reference, url = discover_latest_monthly_xlsx(
        settings=make_settings(tmp_path), session=FakeSession()
    )
    assert reference == "2026-10"
    assert url.startswith("https://www.caixa.gov.br/")
    assert len(fallback_calls) == 1


def test_discovery_probes_official_monthly_zip_when_indexes_are_empty(tmp_path, monkeypatch):
    from getsinapi.collectors import caixa

    class FakeResponse:
        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content
            self.text = "<html></html>"

        def close(self):
            pass

    responses = [
        FakeResponse(200),  # HTML catalog without monthly links
        FakeResponse(404),  # newest candidate is not published
        FakeResponse(200, make_zip()),  # next candidate is a valid official ZIP
    ]
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        return responses.pop(0)

    monkeypatch.setattr(caixa, "_http_get", fake_get)
    reference, url = discover_latest_monthly_xlsx(
        settings=make_settings(tmp_path)
    )
    assert reference == url.split("SINAPI-")[1][:7]
    assert url.startswith("https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/")
    assert len(requested) == 3


def _settings_with_retries(tmp_path, retries=1):
    return Settings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        staging_dir=tmp_path / "data" / "staging",
        processed_dir=tmp_path / "data" / "processed",
        manifest_dir=tmp_path / "data" / "manifests",
        http_timeout=2,
        http_max_retries=retries,
        http_backoff_seconds=0,
    )


def test_download_retries_http_429_then_accepts_valid_zip(tmp_path, monkeypatch):
    from getsinapi.collectors import caixa

    responses = []
    for status in (429, 200):
        response = requests.Response()
        response.status_code = status
        response.raw = BytesIO()
        response.headers["Retry-After"] = "0"
        if status == 200:
            response._content = make_zip()
        responses.append(response)

    class FakeSession:
        def get(self, *args, **kwargs):
            return responses.pop(0)

    monkeypatch.setattr(caixa.time, "sleep", lambda _: None)
    artifact = download_monthly_xlsx(
        "2026-10", settings=_settings_with_retries(tmp_path), session=FakeSession()
    )
    assert artifact.path.is_file()
    assert artifact.size_bytes > 0


@pytest.mark.parametrize("status", [403, 404])
def test_download_does_not_accept_forbidden_or_missing_file(tmp_path, status):
    response = requests.Response()
    response.status_code = status
    response.raw = BytesIO()

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    expected = "HTTP 403" if status == 403 else "HTTP 404"
    with pytest.raises(CaixaDownloadError, match=expected):
        download_monthly_xlsx(
            "2026-10", settings=_settings_with_retries(tmp_path, retries=0),
            session=FakeSession(),
        )
