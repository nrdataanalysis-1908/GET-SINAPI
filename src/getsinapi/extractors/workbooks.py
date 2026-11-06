"""Extração segura e inventário de planilhas XLSX de pacotes SINAPI."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import re
from zipfile import BadZipFile

from openpyxl import load_workbook

from getsinapi.collectors.caixa import CaixaDownloadError, safe_extract_zip
from getsinapi.config import Settings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_workbook(path: Path) -> dict:
    """Retorna metadados das abas sem alterar ou inferir conteúdo de negócio."""
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, OSError, ValueError) as exc:
        raise CaixaDownloadError(f"Planilha XLSX inválida: {path.name}: {exc}") from exc

    sheets = []
    try:
        for worksheet in workbook.worksheets:
            sheets.append({
                "name": worksheet.title,
                "max_row": worksheet.max_row,
                "max_column": worksheet.max_column,
                "state": worksheet.sheet_state,
            })
    finally:
        workbook.close()

    return {
        "file": path.name,
        "relative_path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "sheets": sheets,
    }


def extract_and_catalog(
    archive_path: Path,
    reference: str,
    settings: Settings | None = None,
) -> dict:
    """Extrai um pacote oficial e gera catálogo JSON reproduzível."""
    if not re.fullmatch(r"\\d{4}-(0[1-9]|1[0-2])", reference):
        raise ValueError("Competência inválida. Informe AAAA-MM.")

    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise FileNotFoundError(f"Arquivo ZIP não encontrado: {archive_path}")
    settings = settings or Settings.from_env()
    settings.create_data_directories()

    digest = _sha256(archive_path)
    destination = settings.staging_dir / reference / digest[:12]
    destination.mkdir(parents=True, exist_ok=True)

    extracted = safe_extract_zip(archive_path, destination)
    workbooks = []
    for path in sorted(extracted):
        if path.suffix.lower() == ".xlsx":
            workbooks.append(inspect_workbook(path))

    catalog = {
        "schema_version": "1.0",
        "source_archive": archive_path.name,
        "source_sha256": digest,
        "reference": reference,
        "extracted_at": datetime.now(UTC).isoformat(),
        "extracted_file_count": len(extracted),
        "workbook_count": len(workbooks),
        "files": [
            {"path": path.relative_to(destination).as_posix(), "size_bytes": path.stat().st_size}
            for path in sorted(extracted)
        ],
        "workbooks": workbooks,
    }

    catalog_dir = settings.manifest_dir / reference
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = catalog_dir / f"workbook-catalog-{digest[:12]}.json"
    temporary = catalog_path.with_suffix(".json.part")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(catalog_path)

    return {
        "files": extracted,
        "workbooks": workbooks,
        "catalog_path": catalog_path,
        "catalog": catalog,
    }
