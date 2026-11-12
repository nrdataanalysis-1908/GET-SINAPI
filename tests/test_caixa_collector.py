import hashlib
import stat
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests

from getsinapi.collectors.caixa import (
    CaixaDownloadError,
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


def test_download_repairs_corrupted_existing_archive(tmp_path):
    payload = make_zip()
    response = requests.Response()
    response.status_code = 200
    response._content = payload

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    settings = make_settings(tmp_path)
    first = download_monthly_xlsx("2026-09", settings=settings, session=FakeSession())
    first.path.write_bytes(b"corrupted local cache")

    repaired = download_monthly_xlsx(
        "2026-09", settings=settings, session=FakeSession()
    )

    assert repaired.path.read_bytes() == payload
    assert repaired.sha256 == hashlib.sha256(payload).hexdigest()
    assert repaired.size_bytes == len(payload)


def test_download_rejects_symlinked_archive_target_without_following_target(tmp_path):
    payload = make_zip()
    digest = hashlib.sha256(payload).hexdigest()
    settings = make_settings(tmp_path)
    settings.create_data_directories()
    target = settings.raw_dir / f"SINAPI-2026-09-formato-xlsx-{digest[:12]}.zip"
    protected = tmp_path / "protected.zip"
    protected.write_bytes(b"protected external file")
    target.symlink_to(protected)

    response = requests.Response()
    response.status_code = 200
    response._content = payload

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    with pytest.raises(CaixaDownloadError, match="link simbólico"):
        download_monthly_xlsx("2026-09", settings=settings, session=FakeSession())

    assert protected.read_bytes() == b"protected external file"


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


def test_download_manifest_write_does_not_follow_symlinked_temp_file(tmp_path):
    payload = make_zip()
    digest = hashlib.sha256(payload).hexdigest()
    settings = make_settings(tmp_path)
    settings.create_data_directories()
    manifest_path = settings.manifest_dir / f"2026-09-{digest[:12]}.json"
    manifest_temporary = manifest_path.with_suffix(".json.part")
    protected = tmp_path / "protected-manifest.json"
    protected.write_text("preserve this file", encoding="utf-8")
    manifest_temporary.symlink_to(protected)

    response = requests.Response()
    response.status_code = 200
    response._content = payload

    class FakeSession:
        def get(self, *args, **kwargs):
            return response

    artifact = download_monthly_xlsx(
        "2026-09", settings=settings, session=FakeSession()
    )

    assert protected.read_text(encoding="utf-8") == "preserve this file"
    assert manifest_path.is_file()
    assert not manifest_path.is_symlink()
    assert artifact.sha256 in manifest_path.read_text(encoding="utf-8")


def test_safe_extract_rejects_duplicate_member_paths(tmp_path):
    archive_path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("SINAPI/data.xlsx", b"first")
        archive.writestr("SINAPI/data.xlsx", b"second")

    with pytest.raises(CaixaDownloadError, match="duplicada"):
        safe_extract_zip(archive_path, tmp_path / "out")


def test_safe_extract_rejects_windows_drive_paths(tmp_path):
    archive_path = tmp_path / "drive-path.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("C:/outside.txt", "not allowed")

    with pytest.raises(CaixaDownloadError, match="inseguro"):
        safe_extract_zip(archive_path, tmp_path / "out")


def test_safe_extract_rejects_unix_special_file_types(tmp_path):
    archive_path = tmp_path / "special-file.zip"
    member = zipfile.ZipInfo("SINAPI/pipe")
    member.create_system = 3
    member.external_attr = (stat.S_IFIFO | 0o600) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, b"not a regular file")

    with pytest.raises(CaixaDownloadError, match="inseguro"):
        safe_extract_zip(archive_path, tmp_path / "out")


def test_safe_extract_blocks_zip_slip(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "malicious")

    with pytest.raises(CaixaDownloadError, match="Caminho inseguro"):
        safe_extract_zip(archive_path, tmp_path / "out")
