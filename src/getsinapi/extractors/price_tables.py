"""Parser específico para as tabelas matriciais de preços de insumos SINAPI.

Layout auditado no XLSX oficial: cabeçalhos dos campos e das UFs na linha 10,
com registros a partir da linha 11. As colunas F:AF representam as 27 UFs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from getsinapi.domain import EncargoMode, PriceStatus, Regime
from getsinapi.normalizers import classify_price

REFERENCE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
}
PRICE_TABLES = {
    "ISD": (Regime.NAO_DESONERADO, EncargoMode.COM_ENCARGOS),
    "ICD": (Regime.DESONERADO, EncargoMode.COM_ENCARGOS),
    "ISE": (None, EncargoMode.SEM_ENCARGOS),
}


@dataclass(frozen=True, slots=True)
class InputPriceRecord:
    reference: str
    code: str
    description: str
    unit: str
    uf: str
    regime: Regime | None
    encargo_mode: EncargoMode
    price: Decimal | None
    status: PriceStatus
    price_origin: str | None
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True, slots=True)
class InputPriceParseResult:
    table_type: str
    records: tuple[InputPriceRecord, ...]
    warnings: tuple[str, ...]


def _table_type(path: Path, sheet_name: str) -> str:
    candidates = (path.stem.upper(), sheet_name.upper())
    for candidate in candidates:
        match = re.search(r"(?<![A-Z])(ISD|ICD|ISE)(?![A-Z])", candidate)
        if match:
            return match.group(1)
    raise ValueError("Tipo de tabela não identificado; esperado ISD, ICD ou ISE.")


def _uf(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    match = re.search(r"\b([A-Z]{2})\b", text)
    if match and match.group(1) in UF_CODES:
        return match.group(1)
    return None


def parse_input_price_table(
    workbook_path: str | Path,
    sheet_name: str,
    *,
    reference: str,
) -> InputPriceParseResult:
    """Converte uma tabela ISD/ICD/ISE larga em observações por UF."""
    if not REFERENCE_PATTERN.fullmatch(reference):
        raise ValueError("Competência inválida. Informe AAAA-MM.")
    path = Path(workbook_path)
    table_type = _table_type(path, sheet_name)
    regime, encargo_mode = PRICE_TABLES[table_type]
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Aba inexistente: {sheet_name}")
        sheet = workbook[sheet_name]

        # No XLSX oficial, os rótulos dos campos e as UFs compartilham a linha 10.
        # Streaming sequencial mantém compatibilidade com read_only=True.
        rows = sheet.iter_rows(min_row=10, max_col=32, values_only=True)
        header_row = next(rows, ())
        uf_columns = [
            (column, state)
            for column, value in enumerate(header_row, start=1)
            if column >= 6 and (state := _uf(value)) is not None
        ]
        if len(uf_columns) != 27 or len({state for _, state in uf_columns}) != 27:
            raise ValueError(
                f"Mapa de UFs inválido na linha 10: {len(uf_columns)} colunas reconhecidas."
            )

        headers = [str(value or "").strip().casefold() for value in header_row[:5]]
        if not any("código" in value or "codigo" in value for value in headers):
            raise ValueError("Cabeçalho da tabela não reconhecido na linha 10.")

        records: list[InputPriceRecord] = []
        warnings: list[str] = []
        for row_number, row in enumerate(rows, start=11):
            values = tuple(row)
            code_value = values[1] if len(values) > 1 else None
            description_value = values[2] if len(values) > 2 else None
            unit_value = values[3] if len(values) > 3 else None
            if code_value is None and description_value is None:
                continue
            if code_value is None or description_value is None or unit_value is None:
                warnings.append(f"Linha {row_number}: registro incompleto ignorado.")
                continue

            code = str(code_value).strip()
            description = str(description_value).strip()
            unit = str(unit_value).strip()
            origin_value = values[4] if len(values) > 4 else None
            origin = str(origin_value).strip() if origin_value is not None else None

            for column, state in uf_columns:
                raw_price = values[column - 1] if len(values) >= column else None
                price, status = classify_price(raw_price)
                records.append(InputPriceRecord(
                    reference=reference,
                    code=code,
                    description=description,
                    unit=unit,
                    uf=state,
                    regime=regime,
                    encargo_mode=encargo_mode,
                    price=price,
                    status=status,
                    price_origin=origin,
                    source_file=path.name,
                    source_sheet=sheet_name,
                    source_row=row_number,
                ))

        return InputPriceParseResult(table_type, tuple(records), tuple(warnings))
    finally:
        workbook.close()
