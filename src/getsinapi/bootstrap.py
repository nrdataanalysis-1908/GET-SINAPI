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

import requests

from getsinapi.collectors.caixa import CaixaDownloadError, download_monthly_xlsx, report_url
from getsinapi.config import Settings
from getsinapi.extractors.workbooks import extract_and_catalog
from getsinapi.pipeline.normalize import normalize_reference_workbook
from getsinapi.storage.sqlite import load_silver_reference

log = logging.getLogger("getsinapi.bootstrap")
REQUIRED_SHEETS = {"ISD", "ICD", "ISE", "Analítico"}


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def _discovery_retry_delay(response, attempt: int, settings: Settings) -> float:
    """Respeita Retry-After e aplica backoff exponencial sem martelar a CAIXA."""
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 300.0)
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return min(max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0), 300.0)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(settings.http_backoff_seconds * (2 ** (attempt - 1)), 60.0)


def _reference_exists(reference: str, settings: Settings) -> bool:
    url = report_url(reference)
    headers = {"User-Agent": "GET-SINAPI/0.1 (+https://github.com/nrdataanalysis-1908/GET-SINAPI)"}
    last_status = None

    for attempt in range(1, settings.http_max_retries + 2):
        response = None
        try:
            response = requests.get(
                url, stream=True, timeout=settings.http_timeout, headers=headers,
            )
        except requests.RequestException as exc:
            if attempt > settings.http_max_retries:
                raise CaixaDownloadError(
                    f"Falha de rede ao consultar a competência {reference}: {exc}"
                ) from exc
            time.sleep(_discovery_retry_delay(None, attempt, settings))
            continue

        try:
            last_status = response.status_code
            if response.status_code == 200:
                return True
            if response.status_code == 404:
                return False
            if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                raise CaixaDownloadError(
                    f"CAIXA respondeu HTTP {response.status_code} ao consultar {reference}."
                )
            if attempt > settings.http_max_retries:
                raise CaixaDownloadError(
                    f"CAIXA continua limitando/indisponível (HTTP {response.status_code}) "
                    f"após {settings.http_max_retries} tentativas ao consultar {reference}. "
                    "A atualização pode ser repetida mais tarde."
                )
            delay = _discovery_retry_delay(response, attempt, settings)
        finally:
            response.close()

        log.warning(
            "CAIXA respondeu HTTP %s ao consultar %s; nova tentativa %s/%s em %.1fs.",
            last_status, reference, attempt, settings.http_max_retries, delay,
        )
        time.sleep(delay)

    raise CaixaDownloadError(f"Não foi possível consultar a competência {reference}.")


def discover_latest_reference(settings: Settings, today: date | None = None) -> str:
    current = today or date.today()
    for offset in range(18):
        year, month = _month_shift(current.year, current.month, -offset)
        reference = f"{year:04d}-{month:02d}"
        if _reference_exists(reference, settings):
            return reference
    raise CaixaDownloadError("Nenhuma competência SINAPI publicada foi encontrada nos últimos 18 meses.")


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
        reference = discover_latest_reference(config)
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
            archive = download_monthly_xlsx(reference, settings=config).path

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
