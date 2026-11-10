from __future__ import annotations

from getsinapi.collectors import history


def test_historical_catalog_collects_all_unified_monthly_xlsx(tmp_path, monkeypatch):
    html = """
    <html><body>
      <a href="/Downloads/SINAPI-2025-01-formato-xlsx.zip">Janeiro 2025 XLSX</a>
      <a href="/Downloads/SINAPI-2025-02-formato-xlsx.zip">Fevereiro 2025 XLSX</a>
      <a href="/Downloads/SINAPI-2025-02-formato-pdf.zip">Fevereiro 2025 PDF</a>
      <a href="/Downloads/SINAPI-2024-12-formato-xlsx.zip">Dezembro 2024 XLSX legado</a>
      <a href="https://evil.example/SINAPI-2025-03-formato-xlsx.zip">Fonte externa</a>
    </body></html>
    """

    class FakeResponse:
        status_code = 200
        text = html

        def close(self):
            pass

    monkeypatch.setattr(history, "_http_get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(history, "_from_sharepoint", lambda *args, **kwargs: {})
    catalog = history.discover_historical_xlsx_catalog(
        settings=history.Settings(
            environment="test",
            log_level="INFO",
            data_dir=tmp_path / "data",
            raw_dir=tmp_path / "data/raw",
            staging_dir=tmp_path / "data/staging",
            processed_dir=tmp_path / "data/processed",
            manifest_dir=tmp_path / "data/manifests",
            http_timeout=2,
            http_max_retries=0,
            http_backoff_seconds=0,
        )
    )

    assert list(catalog) == ["2025-01", "2025-02"]
    assert catalog["2025-01"].startswith("https://www.caixa.gov.br/")


def test_historical_catalog_falls_back_to_sharepoint_when_html_is_unavailable(
    tmp_path, monkeypatch
):
    class UnavailableResponse:
        status_code = 503

        def close(self):
            pass

    expected = {"2025-01": "https://www.caixa.gov.br/Downloads/SINAPI-2025-01-formato-xlsx.zip"}
    monkeypatch.setattr(history, "_http_get", lambda *args, **kwargs: UnavailableResponse())
    monkeypatch.setattr(history, "_from_sharepoint", lambda *args, **kwargs: expected)

    settings = history.Settings(
        environment="test", log_level="INFO", data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data/raw", staging_dir=tmp_path / "data/staging",
        processed_dir=tmp_path / "data/processed", manifest_dir=tmp_path / "data/manifests",
        http_timeout=2, http_max_retries=0, http_backoff_seconds=0,
    )
    assert history.discover_historical_xlsx_catalog(settings=settings) == expected
