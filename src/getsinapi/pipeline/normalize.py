"""Publica os resultados normalizados do XLSX oficial na camada Silver."""

from __future__ import annotations

import hashlib
import json
import os
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


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    digest = hashlib.sha256()
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
    os.replace(temporary, path)
    return {
        "file": path.name,
        "records": len(records),
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

    price_records: list[dict[str, Any]] = []
    for table in result.prices:
        for record in table.records:
            price_records.append({
                **asdict(record),
                "table_type": table.table_type,
            })

    composition_records = [asdict(record) for record in result.compositions.compositions]
    item_records = [asdict(record) for record in result.compositions.items]

    artifacts = [
        _write_jsonl(output_dir / "input_prices.jsonl", price_records),
        _write_jsonl(output_dir / "compositions.jsonl", composition_records),
        _write_jsonl(output_dir / "composition_items.jsonl", item_records),
    ]

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
            "input_prices": len(price_records),
            "compositions": len(composition_records),
            "composition_items": len(item_records),
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
