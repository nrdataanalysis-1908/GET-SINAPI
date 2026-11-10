"""Bootstrap histórico, incremental e idempotente da base oficial SINAPI."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
import zipfile
from pathlib import Path

from curl_cffi import requests as browser_requests

from getsinapi.collectors.caixa import CaixaDownloadError, download_monthly_xlsx
from getsinapi.collectors.history import (
    LEGACY_LAYOUT_END,
    UNIFIED_LAYOUT_START,
    discover_historical_xlsx_catalog,
)
from getsinapi.config import Settings
from getsinapi.extractors.workbooks import extract_and_catalog
from getsinapi.pipeline.normalize import normalize_reference_workbook
from getsinapi.storage.sqlite import load_silver_reference

log = logging.getLogger("getsinapi.bootstrap")
_BOOTSTRAP_LOCK = threading.Lock()
DISCOVERY_CACHE_TTL_SECONDS = 6 * 60 * 60
REQUIRED_SHEETS = {"ISD", "ICD", "ISE", "Analítico"}


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    """Desloca uma competência mensal sem depender de datas ou fuso horário."""
    absolute_month = year * 12 + (month - 1) + delta
    shifted_year, zero_based_month = divmod(absolute_month, 12)
    return shifted_year, zero_based_month + 1


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


def _process_reference(
    config: Settings,
    database: Path,
    reference: str,
    source_url: str,
    session,
) -> dict:
    if _loaded_and_complete(database, reference):
        return {"reference": reference, "status": "already_loaded"}

    archive = _find_archive(config, reference)
    if archive is None:
        _write_status(
            config, stage="download", current_reference=reference,
            message=f"Baixando pacote oficial {reference}.",
        )
        archive = download_monthly_xlsx(
            reference, settings=config, source_url=source_url, session=session
        ).path

    catalog_result = _catalog_valid(config, reference, archive)
    if catalog_result is None:
        _write_status(
            config, stage="extraction", current_reference=reference,
            message=f"Extraindo e catalogando {reference}.",
        )
        extracted = extract_and_catalog(archive, reference, settings=config)
        catalog = extracted["catalog"]
        destination = config.staging_dir / reference / _sha256(archive)[:12]
    else:
        catalog, destination = catalog_result

    workbook_path = None
    for entry in catalog.get("workbooks", []):
        sheet_names = {sheet["name"] for sheet in entry.get("sheets", [])}
        if REQUIRED_SHEETS <= sheet_names:
            candidate = destination / entry["relative_path"]
            if candidate.is_file():
                workbook_path = candidate
                break
    if workbook_path is None:
        raise CaixaDownloadError(
            f"O pacote {reference} não contém XLSX com as abas "
            f"oficiais {sorted(REQUIRED_SHEETS)}."
        )

    if not _normalization_valid(config, reference):
        _write_status(
            config, stage="normalization", current_reference=reference,
            message=f"Normalizando preços e composições de {reference}.",
        )
        normalized = normalize_reference_workbook(
            workbook_path, reference=reference, settings=config
        )
    else:
        normalized = json.loads(
            (config.processed_dir / reference / "normalization-manifest.json").read_text(
                encoding="utf-8"
            )
        )

    if not _loaded_and_complete(database, reference):
        _write_status(
            config, stage="database_load", current_reference=reference,
            message=f"Carregando {reference} no SQLite sem remover o histórico existente.",
        )
        loaded = load_silver_reference(config.processed_dir, reference=reference)
    else:
        loaded = {"reference": reference, "database_path": str(database)}

    if not database_is_valid(database) or not _loaded_and_complete(database, reference):
        raise RuntimeError(f"A validação pós-carga de {reference} não foi aprovada.")

    return {
        "reference": reference,
        "status": "loaded",
        "counts": normalized.get("counts", {}),
        "load": loaded,
    }


def _load_discovery_cache(config: Settings, *, force: bool) -> dict[str, str] | None:
    path = config.manifest_dir / "historical-catalog.json"
    if force or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(payload["checked_at"])
        catalog = payload["catalog"]
        if age <= DISCOVERY_CACHE_TTL_SECONDS and isinstance(catalog, dict) and catalog:
            return {str(key): str(value) for key, value in catalog.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None


def _save_discovery_cache(config: Settings, catalog: dict[str, str]) -> None:
    path = config.manifest_dir / "historical-catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"checked_at": time.time(), "catalog": catalog}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _run_bootstrap(settings: Settings | None = None, *, force: bool = False) -> dict:
    config = settings or Settings.from_env()
    config.create_data_directories()
    database = _database_path(config)
    had_database = database_is_valid(database)
    _write_status(
        config, status="checking", stage="discovery", percent=0,
        message="Descobrindo todas as competências XLSX publicadas no catálogo oficial da CAIXA.",
        error=None,
    )
    try:
        with browser_requests.Session(impersonate="chrome") as http_session:
            catalog = _load_discovery_cache(config, force=force)
            if catalog is None:
                catalog = discover_historical_xlsx_catalog(
                    settings=config, session=http_session
                )
                _save_discovery_cache(config, catalog)

            references = sorted(catalog)
            inventory = {
                "schema_version": "1.0",
                "source": "CAIXA",
                "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "layout": "unified-xlsx",
                "covered_from": UNIFIED_LAYOUT_START,
                "legacy_layout_until": LEGACY_LAYOUT_END,
                "references": [
                    {"reference": reference, "url": catalog[reference]}
                    for reference in references
                ],
            }
            inventory_path = config.manifest_dir / "historical-inventory.json"
            inventory_tmp = inventory_path.with_suffix(".json.tmp")
            inventory_tmp.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            inventory_tmp.replace(inventory_path)

            outcomes = []
            failures = []
            for index, reference in enumerate(references, start=1):
                percent = round((index - 1) / max(len(references), 1) * 100)
                _write_status(
                    config, status="running", stage="historical_ingestion",
                    percent=percent, current_reference=reference,
                    completed=len(outcomes), total=len(references),
                    message=f"Processando competência {reference} ({index}/{len(references)}).",
                )
                try:
                    result = _process_reference(
                        config, database, reference, catalog[reference], http_session
                    )
                    outcomes.append(result)
                except Exception as exc:
                    log.exception("Falha ao processar competência histórica %s", reference)
                    failures.append({
                        "reference": reference,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    _write_status(
                        config, status="running", stage="historical_ingestion",
                        current_reference=reference, failed=len(failures),
                        message=f"Falha em {reference}; continuando as demais competências.",
                    )

        loaded_references = [
            item["reference"] for item in outcomes
            if item["status"] in {"loaded", "already_loaded"}
        ]
        legacy_pending = True
        result = {
            "status": "partial" if legacy_pending or failures else "complete",
            "database": str(database),
            "discovered": len(references),
            "loaded_or_verified": len(loaded_references),
            "failed": failures,
            "references": loaded_references,
            "covered_from": UNIFIED_LAYOUT_START,
            "legacy_history_pending": legacy_pending,
            "legacy_layout_until": LEGACY_LAYOUT_END,
            "previous_database_preserved": had_database,
        }
        if failures:
            result["status"] = "partial"
        _write_status(
            config, **result, stage="partial" if legacy_pending or failures else "complete",
            percent=100, current_reference=None,
            message=(
                "Pacotes XLSX unificados processados. O histórico legado até 2024 "
                "ainda exige ingestão por UF e parser próprio."
            ),
            error=None if not failures else "Uma ou mais competências não foram processadas.",
        )
        return result
    except Exception as exc:
        log.exception("Falha na descoberta/ingestão histórica SINAPI")
        _write_status(
            config, status="error", stage="error", percent=None,
            message="Ingestão interrompida; os dados históricos já persistidos foram preservados.",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise


def run_bootstrap(settings: Settings | None = None, *, force: bool = False) -> dict:
    """Executa uma única atualização histórica por processo; chamadas concorrentes são coalescidas."""
    if not _BOOTSTRAP_LOCK.acquire(blocking=False):
        return {"status": "already_running", "message": "A atualização SINAPI já está em andamento."}
    try:
        return _run_bootstrap(settings, force=force)
    finally:
        _BOOTSTRAP_LOCK.release()
