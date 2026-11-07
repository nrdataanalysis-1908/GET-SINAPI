"""Parser específico para as tabelas matriciais de preços de insumos SINAPI.

Layout auditado: cabeçalho de UFs na linha 9, cabeçalho de campos na linha 10
e registros a partir da linha 11. As colunas F:AF representam as 27 UFs.
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
    path = Path(workbook_path)
    table_type = _table_type(path, sheet_name)
    regime, encargo_mode = PRICE_TABLES[table_type]
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Aba inexistente: {sheet_name}")
        sheet = workbook[sheet_name]

        # A linha 9 contém as siglas das UFs alinhadas às colunas de preços F:AF.
        uf_columns: list[tuple[int, str]] = []
        for column in range(6, 33):
            state = _uf(sheet.cell(row=9, column=column).value)
            if state:
                uf_columns.append((column, state))
        if len(uf_columns) != 27 or len({state for _, state in uf_columns}) != 27:
            raise ValueError(
                f"Mapa de UFs inválido na linha 9: {len(uf_columns)} colunas reconhecidas."
            )

        headers = [str(sheet.cell(row=10, column=column).value or "").strip().casefold()
                   for column in range(1, 6)]
        if not any("código" in value or "codigo" in value for value in headers):
            raise ValueError("Cabeçalho da tabela não reconhecido na linha 10.")

        records: list[InputPriceRecord] = []
        warnings: list[str] = []
        for row_number in range(11, (sheet.max_row or 10) + 1):
            code_value = sheet.cell(row=row_number, column=2).value
            description_value = sheet.cell(row=row_number, column=3).value
            unit_value = sheet.cell(row=row_number, column=4).value
            if code_value is None and description_value is None:
                continue
            if code_value is None or description_value is None or unit_value is None:
                warnings.append(f"Linha {row_number}: registro incompleto ignorado.")
                continue

            code = str(code_value).strip()
            description = str(description_value).strip()
            unit = str(unit_value).strip()
            origin_value = sheet.cell(row=row_number, column=5).value
            origin = str(origin_value).strip() if origin_value is not None else None

            for column, state in uf_columns:
                raw_price = sheet.cell(row=row_number, column=column).value
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
