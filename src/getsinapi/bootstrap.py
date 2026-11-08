"""Bootstrap incremental e idempotente da base oficial SINAPI."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

from curl_cffi import requests as browser_requests

from getsinapi.collectors.caixa import (
    CaixaDownloadError,
    discover_latest_monthly_xlsx,
    download_monthly_xlsx,
)
from getsinapi.config import Settings
from getsinapi.extractors.workbooks import extract_and_catalog
from getsinapi.pipeline.normalize import normalize_reference_workbook
from getsinapi.storage.sqlite import load_silver_reference

log = logging.getLogger("getsinapi.bootstrap")
REQUIRED_SHEETS = {"ISD", "ICD", "ISE", "Analítico"}


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def discover_latest_reference(settings: Settings, today: date | None = None) -> str:
    """Retorna a competência mais recente listada no catálogo oficial da CAIXA."""
    del today  # A fonte oficial, e não o calendário, determina a competência publicada.
    reference, _ = discover_latest_monthly_xlsx(settings=settings)
    return reference


def discover_latest_report(settings: Settings) -> tuple[str, str]:
    """Retorna competência e URL XLSX exata encontrada no catálogo oficial."""
    return discover_latest_monthly_xlsx(settings=settings)


def _database_path(settings: Settings) -> Path:
    return settings.data_dir / "getsinapi.sqlite3"


def database_is_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            required = {"source_references", "input_prices", "compositions", "composition_items"}
            if not required <= tables:
                return False
            return db.execute("SELECT COUNT(*) FROM source_references").fetchone()[0] > 0
    except (sqlite3.Error, OSError):
        return False


def _loaded_and_complete(database: Path, reference: str) -> bool:
    if not database_is_valid(database):
        return False
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5) as db:
            source = db.execute(
                "SELECT 1 FROM source_references WHERE reference=?", (reference,)
            ).fetchone()
            if not source:
                return False
            prices, compositions, items = db.execute(
                """SELECT
                    (SELECT COUNT(*) FROM input_prices WHERE reference=?),
                    (SELECT COUNT(*) FROM compositions WHERE reference=?),
                    (SELECT COUNT(*) FROM composition_items WHERE reference=?)""",
                (reference, reference, reference),
            ).fetchone()
            return prices > 0 and compositions > 0 and items > 0
    except sqlite3.Error:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_archive(settings: Settings, reference: str) -> Path | None:
    for path in sorted(settings.raw_dir.glob(f"SINAPI-{reference}-formato-xlsx-*.zip")):
        if zipfile.is_zipfile(path):
            return path
    return None


def _catalog_valid(settings: Settings, reference: str, archive: Path) -> tuple[dict, Path] | None:
    digest = _sha256(archive)
    catalog_path = settings.manifest_dir / reference / f"workbook-catalog-{digest[:12]}.json"
    destination = settings.staging_dir / reference / digest[:12]
    if not catalog_path.is_file():
        return None
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog.get("reference") != reference or catalog.get("source_sha256") != digest:
            return None
        for entry in catalog.get("files", []):
            file_path = destination / entry["path"]
            if not file_path.is_file() or file_path.stat().st_size != entry["size_bytes"]:
                return None
        return catalog, destination
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _normalization_valid(settings: Settings, reference: str) -> bool:
    folder = settings.processed_dir / reference
    manifest_path = folder / "normalization-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("reference") != reference:
            return False
        artifacts = {item["file"]: item for item in manifest["artifacts"]}
        expected = {"input_prices.jsonl", "compositions.jsonl", "composition_items.jsonl"}
        if set(artifacts) != expected:
            return False
        for name, metadata in artifacts.items():
            path = folder / name
            if not path.is_file() or path.stat().st_size != metadata["size_bytes"]:
                return False
            if _sha256(path) != metadata["sha256"]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _write_status(settings: Settings, **values) -> None:
    path = settings.data_dir / "logs" / "bootstrap-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    current.update(values)
    current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_bootstrap(settings: Settings | None = None) -> dict:
    config = settings or Settings.from_env()
    config.create_data_directories()
    database = _database_path(config)
    had_database = database_is_valid(database)
    _write_status(config, status="checking", stage="discovery", percent=None,
                  message="Consultando a competência oficial mais recente.", error=None)
    try:
        # Mantém cookies e fingerprint do navegador entre catálogo e download.
        # A CAIXA pode bloquear o download quando a sessão é iniciada diretamente no ZIP.
        with browser_requests.Session(impersonate="chrome") as http_session:
            reference, source_url = discover_latest_monthly_xlsx(
                settings=config, session=http_session,
            )
            _write_status(config, reference=reference, stage="integrity",
                          message=f"Competência oficial identificada: {reference}.")
            if _loaded_and_complete(database, reference):
                result = {"status": "up_to_date", "reference": reference, "database": str(database)}
                _write_status(config, **result, stage="complete", percent=100,
                              message="Base íntegra e atualizada; nenhuma carga foi repetida.")
                return result

            archive = _find_archive(config, reference)
            if archive is None:
                _write_status(config, stage="download", percent=None,
                              message=f"Baixando pacote oficial {reference}.")
                archive = download_monthly_xlsx(
                    reference, settings=config, source_url=source_url,
                    session=http_session,
                ).path

        catalog_result = _catalog_valid(config, reference, archive)
        if catalog_result is None:
            _write_status(config, stage="extraction", percent=None,
                          message=f"Extraindo e catalogando {reference}.")
            extracted = extract_and_catalog(archive, reference, settings=config)
            catalog, destination = extracted["catalog"], config.staging_dir / reference / _sha256(archive)[:12]
        else:
            catalog, destination = catalog_result

        workbook_path = None
        for entry in catalog.get("workbooks", []):
            if set(sheet["name"] for sheet in entry.get("sheets", [])) >= REQUIRED_SHEETS:
                candidate = destination / entry["relative_path"]
                if candidate.is_file():
                    workbook_path = candidate
                    break
        if workbook_path is None:
            raise CaixaDownloadError(
                f"O pacote {reference} não contém XLSX com as abas oficiais {sorted(REQUIRED_SHEETS)}."
            )

        if not _normalization_valid(config, reference):
            _write_status(config, stage="normalization", percent=None,
                          message=f"Normalizando preços e composições de {reference}.")
            normalized = normalize_reference_workbook(
                workbook_path, reference=reference, settings=config
            )
        else:
            normalized = json.loads(
                (config.processed_dir / reference / "normalization-manifest.json").read_text(encoding="utf-8")
            )

        if not _loaded_and_complete(database, reference):
            _write_status(config, stage="database_load", percent=None,
                          message=f"Atualizando SQLite sem remover competências históricas: {reference}.")
            loaded = load_silver_reference(config.processed_dir, reference=reference)
        else:
            loaded = {"reference": reference, "database_path": str(database)}

        if not database_is_valid(database) or not _loaded_and_complete(database, reference):
            raise RuntimeError("A validação pós-carga do SQLite não foi aprovada.")
        result = {"status": "updated", "reference": reference,
                  "database": str(database), "counts": normalized.get("counts", {}),
                  "load": loaded, "previous_database_preserved": had_database}
        _write_status(config, **result, stage="complete", percent=100,
                      message=f"Base SINAPI atualizada e validada na competência {reference}.",
                      error=None)
        return result
    except Exception as exc:
        log.exception("Falha no bootstrap SINAPI")
        _write_status(config, status="error", stage="error", percent=None,
                      message="Atualização interrompida; a base histórica existente foi preservada.",
                      error=f"{type(exc).__name__}: {exc}")
        raise
