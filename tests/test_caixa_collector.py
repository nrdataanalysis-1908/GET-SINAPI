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

    with pytest.raises(CaixaDownloadError, match="catálogo oficial.*HTTP 403"):
        discover_latest_monthly_xlsx(
            settings=make_settings(tmp_path), session=FakeSession()
        )


def test_discovery_rejects_non_caixa_download_links(tmp_path):
    class FakeResponse:
        status_code = 200
        text = '<a href="https://evil.example/SINAPI-2026-10-formato-xlsx.zip">XLSX</a>'

        def close(self):
            pass

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(CaixaDownloadError, match="nenhum link mensal XLSX"):
        discover_latest_monthly_xlsx(
            settings=make_settings(tmp_path), session=FakeSession()
        )
