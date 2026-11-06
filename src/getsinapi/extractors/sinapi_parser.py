"""Parser configurável para planilhas SINAPI catalogadas.

A detecção de colunas é conservadora: só mapeia cabeçalhos conhecidos.
Nenhuma coluna ou regime é inferido apenas pela posição da coluna.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from getsinapi.domain import PriceObservation, Regime
from getsinapi.normalizers import classify_price


HEADER_ALIASES = {
    "code": {"codigo", "cod", "codigo do insumo", "codigo da composicao"},
    "description": {"descricao", "descricao do insumo", "descricao da composicao"},
    "unit": {"unidade", "un"},
    "price": {"preco", "preco mediano", "custo"},
    "status": {"situacao", "observacao", "status", "nota"},
}
UF_PATTERN = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
)


@dataclass(frozen=True, slots=True)
class SheetParseResult:
    sheet_name: str
    regime: Regime | None
    uf: str | None
    header_row: int | None
    records: tuple[PriceObservation, ...]
    warnings: tuple[str, ...]


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9 ]", " ", text)).strip().lower()


def detect_regime(sheet_name: str) -> Regime | None:
    normalized = normalize_header(sheet_name)
    if "nao desonerado" in normalized or "nao desonerada" in normalized:
        return Regime.NAO_DESONERADO
    if "desonerado" in normalized or "desonerada" in normalized:
        return Regime.DESONERADO
    return None


def detect_uf(*values: Any) -> str | None:
    text = " ".join(str(value) for value in values if value is not None).upper()
    matches = UF_PATTERN.findall(text)
    return matches[0] if len(set(matches)) == 1 else None


def _column_map(row: tuple[Any, ...]) -> dict[str, int]:
    normalized = [normalize_header(value) for value in row]
    result: dict[str, int] = {}
    for field, aliases in HEADER_ALIASES.items():
        matches = [index for index, value in enumerate(normalized) if value in aliases]
        if len(matches) == 1:
            result[field] = matches[0]
    return result


def _cell(row: tuple[Any, ...], columns: dict[str, int], field: str) -> Any:
    index = columns.get(field)
    return row[index] if index is not None and index < len(row) else None


def parse_worksheet(
    workbook_path: str | Path,
    sheet_name: str,
    *,
    reference: str,
    source_file: str | None = None,
) -> SheetParseResult:
    path = Path(workbook_path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Aba inexistente: {sheet_name}")
        sheet = workbook[sheet_name]
        regime = detect_regime(sheet_name)
        rows = sheet.iter_rows(values_only=True)
        header_row = None
        columns: dict[str, int] = {}
        uf: str | None = None
        context_rows: list[Any] = []

        for row_number, row in enumerate(rows, start=1):
            context_rows.extend(row)
            candidate = _column_map(tuple(row))
            if {"code", "description", "unit", "price"}.issubset(candidate):
                header_row = row_number
                columns = candidate
                uf = detect_uf(*context_rows)
                break

        if header_row is None:
            return SheetParseResult(
                sheet_name,
                regime,
                None,
                None,
                (),
                ("Cabeçalho não reconhecido; layout requer mapeamento explícito.",),
            )

        records: list[PriceObservation] = []
        warnings: list[str] = []
        for row_number, row in enumerate(rows, start=header_row + 1):
            values = tuple(row)
            code = _cell(values, columns, "code")
            description = _cell(values, columns, "description")
            unit = _cell(values, columns, "unit")
            raw_price = _cell(values, columns, "price")
            raw_status = _cell(values, columns, "status")
            if code is None and description is None:
                continue
            if code is None or description is None or unit is None:
                warnings.append(f"Linha {row_number}: registro incompleto ignorado.")
                continue
            if uf is None or regime is None:
                warnings.append(
                    f"Linha {row_number}: UF ou regime não identificados; registro não emitido."
                )
                continue
            price, status = classify_price(raw_price, raw_status)
            records.append(
                PriceObservation(
                    reference=reference,
                    uf=uf,
                    regime=regime,
                    code=str(code).strip(),
                    description=str(description).strip(),
                    unit=str(unit).strip(),
                    price=price,
                    status=status,
                    source_file=source_file or path.name,
                    source_sheet=sheet_name,
                    source_row=row_number,
                )
            )
        return SheetParseResult(
            sheet_name, regime, uf, header_row, tuple(records), tuple(warnings)
        )
    finally:
        workbook.close()
