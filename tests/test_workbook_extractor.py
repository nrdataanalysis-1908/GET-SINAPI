import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook

from getsinapi.config import Settings
from getsinapi.extractors.workbooks import extract_and_catalog, inspect_workbook


def make_settings(root: Path) -> Settings:
    data = root / "data"
    return Settings(
        environment="test",
        log_level="INFO",
        data_dir=data,
        raw_dir=data / "raw",
        staging_dir=data / "staging",
        processed_dir=data / "processed",
        manifest_dir=data / "manifests",
        http_timeout=2,
        http_max_retries=0,
        http_backoff_seconds=0,
    )


def make_xlsx(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Insumos Não Desonerados"
    sheet.append(["Código", "Descrição", "Unidade", "Preço"])
    sheet.append(["00001234", "Material de teste", "UN", 0])
    workbook.save(path)


def test_inspect_workbook_reports_sheet_metadata(tmp_path):
    path = tmp_path / "sample.xlsx"
    make_xlsx(path)

    result = inspect_workbook(path)

    assert result["sheets"][0]["name"] == "Insumos Não Desonerados"
    assert result["sheets"][0]["max_row"] == 2
    assert result["sheets"][0]["preview_rows"][0] == ["Código", "Descrição", "Unidade", "Preço"]
    assert result["sheets"][0]["preview_rows"][1][-1] == 0
    assert result["sha256"]


def test_extract_and_catalog_creates_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    workbook_path = source / "SINAPI_Referencia.xlsx"
    make_xlsx(workbook_path)

    archive = tmp_path / "package.zip"
    with ZipFile(archive, "w") as zipped:
        zipped.write(workbook_path, "relatorios/SINAPI_Referencia.xlsx")

    result = extract_and_catalog(archive, "2026-09", settings=make_settings(tmp_path))

    assert len(result["files"]) == 1
    assert result["workbooks"][0]["sheets"][0]["name"] == "Insumos Não Desonerados"
    manifest = json.loads(result["catalog_path"].read_text(encoding="utf-8"))
    assert manifest["source_sha256"]
    assert manifest["reference"] == "2026-09"


def test_extract_rejects_invalid_reference(tmp_path):
    archive = tmp_path / "x.zip"
    archive.write_bytes(b"")
    try:
        extract_and_catalog(archive, "2026-13", settings=make_settings(tmp_path))
    except ValueError as exc:
        assert "Competência inválida" in str(exc)
    else:
        raise AssertionError("Competência inválida deveria ser rejeitada.")
