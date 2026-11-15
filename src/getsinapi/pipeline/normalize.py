"""Publica os resultados normalizados do XLSX oficial na camada Silver."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import asdict
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from getsinapi.config import Settings
from getsinapi.extractors.reference_workbook import parse_reference_workbook


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    digest = hashlib.sha256()
    record_count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            line = json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                default=_json_default,
                separators=(",", ":"),
            ) + "\n"
            stream.write(line)
            digest.update(line.encode("utf-8"))
            record_count += 1
    os.replace(temporary, path)
    return {
        "file": path.name,
        "records": record_count,
        "sha256": digest.hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def normalize_reference_workbook(
    workbook_path: str | Path,
    *,
    reference: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Extrai tabelas e grava JSONL rastreável em data/processed/AAAA-MM."""
    config = settings or Settings.from_env()
    result = parse_reference_workbook(workbook_path, reference=reference)
    output_dir = config.processed_dir / reference

    # Não materializa cópias adicionais de centenas de milhares de registros
    # como listas de dicionários; serializa cada registro diretamente em JSONL.
    def iter_price_records():
        for table in result.prices:
            for record in table.records:
                yield {**asdict(record), "table_type": table.table_type}

    artifacts = [
        _write_jsonl(output_dir / "input_prices.jsonl", iter_price_records()),
        _write_jsonl(
            output_dir / "compositions.jsonl",
            (asdict(record) for record in result.compositions.compositions),
        ),
        _write_jsonl(
            output_dir / "composition_items.jsonl",
            (asdict(record) for record in result.compositions.items),
        ),
    ]
    counts_by_file = {item["file"]: item["records"] for item in artifacts}

    warnings = [
        {"source": table.table_type, "message": warning}
        for table in result.prices
        for warning in table.warnings
    ] + [
        {"source": "Analítico", "message": warning}
        for warning in result.compositions.warnings
    ]

    manifest = {
        "reference": reference,
        "source_file": result.source_file,
        "source_path": str(Path(workbook_path)),
        "artifacts": artifacts,
        "counts": {
            "input_prices": counts_by_file["input_prices.jsonl"],
            "compositions": counts_by_file["compositions.jsonl"],
            "composition_items": counts_by_file["composition_items.jsonl"],
        },
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    manifest_path = output_dir / "normalization-manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_manifest, manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest
