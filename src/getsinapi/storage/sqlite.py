"""Persistência histórica idempotente em SQLite para desenvolvimento e análise local.

O contrato relacional é independente do mecanismo; a migração para PostgreSQL
pode preservar tabelas, chaves naturais e semântica de carga.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_references (
    reference TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS input_prices (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    uf TEXT NOT NULL,
    regime TEXT,
    encargo_mode TEXT NOT NULL,
    table_type TEXT NOT NULL,
    price TEXT,
    status TEXT NOT NULL,
    price_origin TEXT,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(reference, code, uf, regime, encargo_mode, table_type),
    FOREIGN KEY(reference) REFERENCES source_references(reference)
);

CREATE INDEX IF NOT EXISTS idx_input_prices_lookup
ON input_prices(reference, uf, regime, encargo_mode, code);

CREATE TABLE IF NOT EXISTS compositions (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    status TEXT,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(reference, code),
    FOREIGN KEY(reference) REFERENCES source_references(reference)
);

CREATE TABLE IF NOT EXISTS composition_items (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL,
    composition_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_type TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    coefficient TEXT NOT NULL,
    status TEXT,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    UNIQUE(reference, composition_code, source_row),
    FOREIGN KEY(reference, composition_code)
        REFERENCES compositions(reference, code)
);

CREATE INDEX IF NOT EXISTS idx_composition_items_parent
ON composition_items(reference, composition_code);

CREATE INDEX IF NOT EXISTS idx_composition_items_child
ON composition_items(reference, item_code, item_type);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)

    item_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(composition_items)")
    }
    if "status" not in item_columns:
        connection.execute("ALTER TABLE composition_items ADD COLUMN status TEXT")

    duplicate = connection.execute(
        """SELECT reference, code, uf, COALESCE(regime, ''), encargo_mode, table_type,
                  COUNT(*) AS occurrences
           FROM input_prices
           GROUP BY reference, code, uf, COALESCE(regime, ''), encargo_mode, table_type
           HAVING COUNT(*) > 1 LIMIT 1"""
    ).fetchone()
    if duplicate is not None:
        raise ValueError(
            "Chave natural de preços duplicada no banco existente; "
            "reconcilie os registros antes de criar a restrição idempotente."
        )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_input_prices_natural_key
           ON input_prices(
               reference, code, uf, COALESCE(regime, ''), encargo_mode, table_type
           )"""
    )


def initialize_database(database_path: str | Path) -> None:
    with connect(database_path) as connection:
        _ensure_schema(connection)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Artefato Silver não encontrado: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL inválido em {path.name}, linha {line_number}.") from exc
            if not isinstance(record, dict):
                raise TypeError(f"Registro JSONL deve ser objeto: {path.name}:{line_number}.")
            records.append(record)
    return records


def load_silver_reference(
    processed_dir: str | Path,
    *,
    reference: str,
) -> dict[str, int | str]:
    """Carrega uma competência em transação única; repetir a carga não duplica."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", reference):
        raise ValueError("Competência inválida. Informe AAAA-MM.")
    base = Path(processed_dir) / reference
    manifest_path = base / "normalization-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifesto Silver não encontrado: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("reference") != reference:
        raise ValueError("Competência do manifesto diverge da solicitada.")

    expected_files = {
        "input_prices.jsonl", "compositions.jsonl", "composition_items.jsonl"
    }
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("Manifesto Silver sem inventário de artefatos válido.")
    metadata = {entry.get("file"): entry for entry in artifacts if isinstance(entry, dict)}
    if set(metadata) != expected_files or len(metadata) != len(artifacts):
        raise ValueError("Inventário de artefatos Silver incompleto ou inconsistente.")

    collections: dict[str, list[dict[str, Any]]] = {}
    for filename in sorted(expected_files):
        path = base / filename
        artifact = metadata[filename]
        if not path.is_file():
            raise FileNotFoundError(f"Artefato Silver não encontrado: {path}")
        if path.stat().st_size != artifact.get("size_bytes"):
            raise ValueError(f"Tamanho divergente no artefato Silver: {filename}.")
        if _sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"SHA-256 divergente no artefato Silver: {filename}.")
        records = _read_jsonl(path)
        if len(records) != artifact.get("records"):
            raise ValueError(f"Quantidade de registros divergente no artefato Silver: {filename}.")
        collections[filename] = records

    prices = collections["input_prices.jsonl"]
    compositions = collections["compositions.jsonl"]
    items = collections["composition_items.jsonl"]
    for collection in (prices, compositions, items):
        if any(record.get("reference") != reference for record in collection):
            raise ValueError("Há registros com competência divergente nos artefatos Silver.")

    database_path = Path(processed_dir).parent / "getsinapi.sqlite3"
    with connect(database_path) as connection:
        _ensure_schema(connection)
        connection.execute(
            """INSERT INTO source_references(reference, source_file)
               VALUES (?, ?)
               ON CONFLICT(reference) DO UPDATE SET
               source_file=excluded.source_file, loaded_at=CURRENT_TIMESTAMP""",
            (reference, manifest["source_file"]),
        )

        # Substitui apenas a competência solicitada, preservando todo o histórico.
        connection.execute("DELETE FROM input_prices WHERE reference = ?", (reference,))
        connection.execute("DELETE FROM composition_items WHERE reference = ?", (reference,))
        connection.execute("DELETE FROM compositions WHERE reference = ?", (reference,))

        connection.executemany(
            """INSERT INTO compositions(
                reference, code, description, unit, status,
                source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    row["reference"], row["code"], row["description"], row["unit"],
                    row.get("status"), row["source_file"], row["source_sheet"],
                    row["source_row"],
                )
                for row in compositions
            ],
        )
        connection.executemany(
            """INSERT INTO composition_items(
                reference, composition_code, item_code, item_type, description,
                unit, coefficient, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    row["reference"], row["composition_code"], row["item_code"],
                    row["item_type"], row["description"], row["unit"],
                    str(row["coefficient"]), row.get("status"), row["source_file"],
                    row["source_sheet"], row["source_row"],
                )
                for row in items
            ],
        )
        connection.executemany(
            """INSERT INTO input_prices(
                reference, code, description, unit, uf, regime, encargo_mode,
                table_type, price, status, price_origin, source_file,
                source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    row["reference"], row["code"], row["description"], row["unit"],
                    row["uf"], row.get("regime"), row["encargo_mode"],
                    row["table_type"], row.get("price"), row["status"],
                    row.get("price_origin"), row["source_file"], row["source_sheet"],
                    row["source_row"],
                )
                for row in prices
            ],
        )

        return {
            "reference": reference,
            "database_path": str(database_path),
            "input_prices": len(prices),
            "compositions": len(compositions),
            "composition_items": len(items),
        }
