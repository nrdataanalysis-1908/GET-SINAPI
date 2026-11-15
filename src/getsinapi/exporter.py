"""Exportação em lote do catálogo SINAPI para Excel e CSV."""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from openpyxl import Workbook

CATEGORIES = {
    "INSUMO": "Insumos",
    "COMPOSICAO": "Composicoes",
    "COMPONENTE": "Componentes",
}
EXCEL_MAX_DATA_ROWS = 1_048_575

CATALOG_CTE = """
WITH catalog AS (
    SELECT reference, 'INSUMO' AS record_type, code, description, unit, uf,
           regime, encargo_mode, table_type, price AS value, 'PRECO' AS value_type,
           NULL AS composition_code, status, source_file, source_sheet, source_row
    FROM input_prices
    UNION ALL
    SELECT reference, 'COMPOSICAO', code, description, unit,
           NULL, NULL, NULL, 'Analitico', NULL, NULL, NULL,
           status, source_file, source_sheet, source_row
    FROM compositions
    UNION ALL
    SELECT reference, 'COMPONENTE', item_code, description, unit,
           NULL, NULL, NULL, 'Analitico', coefficient, 'COEFICIENTE',
           composition_code, status, source_file, source_sheet, source_row
    FROM composition_items
)
"""

COLUMNS = (
    "reference", "record_type", "code", "description", "unit", "uf", "regime",
    "encargo_mode", "table_type", "value", "value_type", "composition_code",
    "status", "source_file", "source_sheet", "source_row",
)


def _query(
    *,
    references: list[str] | None,
    uf: str | None,
    categories: list[str],
    regime: str | None,
    encargo_mode: str | None,
    search: str | None,
) -> tuple[str, tuple[Any, ...]]:
    clauses: list[str] = []
    params: list[Any] = []
    if references:
        clauses.append("reference IN (" + ",".join("?" for _ in references) + ")")
        params.extend(references)
    if uf:
        clauses.append("(uf = ? OR uf IS NULL)")
        params.append(uf.upper())
    if categories:
        clauses.append("record_type IN (" + ",".join("?" for _ in categories) + ")")
        params.extend(categories)
    if regime:
        clauses.append("(regime = ? OR regime IS NULL)")
        params.append(regime)
    if encargo_mode:
        clauses.append("(encargo_mode = ? OR encargo_mode IS NULL)")
        params.append(encargo_mode)
    if search:
        term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append(
            "(code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "OR composition_code LIKE ? ESCAPE '\\')"
        )
        params.extend((term, term, term))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = CATALOG_CTE + " SELECT " + ", ".join(COLUMNS) + " FROM catalog" + where
    return sql, tuple(params)


def available_references(database_path: Path) -> list[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
        ).fetchall()
    return [str(row[0]) for row in rows]


def export_catalog(
    database_path: Path,
    output_dir: Path,
    *,
    file_format: str,
    references: list[str] | None = None,
    uf: str | None = None,
    categories: list[str] | None = None,
    regime: str | None = None,
    encargo_mode: str | None = None,
    search: str | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> list[Path]:
    """Exporta categorias individualizadas e uma visão consolidada."""
    if file_format not in {"xlsx", "csv", "both"}:
        raise ValueError("Formato deve ser xlsx, csv ou both.")
    selected = categories or list(CATEGORIES)
    invalid = set(selected) - set(CATEGORIES)
    if invalid:
        raise ValueError(f"Categorias inválidas: {', '.join(sorted(invalid))}.")
    if not database_path.is_file():
        raise FileNotFoundError(f"Banco SINAPI não encontrado: {database_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = output_dir / f"getsinapi_export_{stamp}"
    sql, params = _query(
        references=references, uf=uf, categories=selected, regime=regime,
        encargo_mode=encargo_mode, search=search
    )
    generated: list[Path] = []

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        if file_format in {"xlsx", "both"}:
            workbook = Workbook(write_only=True)
            sheets: dict[str, Any] = {}

            def new_sheet(label: str, index: int = 1):
                suffix = f"_{index:02d}" if index > 1 else ""
                sheet = workbook.create_sheet((label[:25] + suffix)[:31])
                sheet.append(list(COLUMNS))
                return sheet

            sheets["CONSOLIDADO"] = new_sheet("CONSOLIDADO")
            for category in selected:
                sheets[category] = new_sheet(CATEGORIES[category])

            cursor = connection.execute(sql, params)
            counts = {key: 0 for key in sheets}
            sheet_parts = {key: 1 for key in sheets}
            processed = 0
            while rows := cursor.fetchmany(2000):
                for row in rows:
                    values = [row[column] for column in COLUMNS]
                    category = str(row["record_type"])
                    for key in ("CONSOLIDADO", category):
                        if key not in sheets:
                            continue
                        if counts[key] >= EXCEL_MAX_DATA_ROWS:
                            sheet_parts[key] += 1
                            label = "CONSOLIDADO" if key == "CONSOLIDADO" else CATEGORIES[key]
                            sheets[key] = new_sheet(label, sheet_parts[key])
                            counts[key] = 0
                        sheets[key].append(values)
                        counts[key] += 1
                    processed += 1
                if progress_callback is not None:
                    progress_callback("Excel", processed)
            xlsx_path = base.with_suffix(".xlsx")
            workbook.save(xlsx_path)
            generated.append(xlsx_path)

        if file_format in {"csv", "both"}:
            csv_targets = {"CONSOLIDADO": base.with_name(base.name + "_consolidado.csv")}
            csv_targets.update({
                category: base.with_name(base.name + "_" + CATEGORIES[category].lower() + ".csv")
                for category in selected
            })
            handles = {}
            writers = {}
            try:
                for key, path in csv_targets.items():
                    handle = path.open("w", newline="", encoding="utf-8-sig")
                    handles[key] = handle
                    writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_MINIMAL)
                    writer.writerow(COLUMNS)
                    writers[key] = writer
                cursor = connection.execute(sql, params)
                processed = 0
                while rows := cursor.fetchmany(2000):
                    for row in rows:
                        values = [row[column] for column in COLUMNS]
                        writers["CONSOLIDADO"].writerow(values)
                        category = str(row["record_type"])
                        if category in writers:
                            writers[category].writerow(values)
                        processed += 1
                    if progress_callback is not None:
                        progress_callback("CSV", processed)
            finally:
                for handle in handles.values():
                    handle.close()
            generated.extend(csv_targets.values())

    return generated
