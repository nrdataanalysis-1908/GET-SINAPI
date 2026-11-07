"""Orquestra a leitura das tabelas oficiais de referência SINAPI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from getsinapi.extractors.compositions import (
    CompositionParseResult,
    parse_analytic_compositions,
)
from getsinapi.extractors.price_tables import (
    InputPriceParseResult,
    parse_input_price_table,
)

PRICE_SHEETS = ("ISD", "ICD", "ISE")
COMPOSITION_SHEET = "Analítico"


@dataclass(frozen=True, slots=True)
class ReferenceWorkbookResult:
    reference: str
    source_file: str
    prices: tuple[InputPriceParseResult, ...]
    compositions: CompositionParseResult


def parse_reference_workbook(
    workbook_path: str | Path,
    *,
    reference: str,
) -> ReferenceWorkbookResult:
    """Extrai preços ISD/ICD/ISE e estrutura Analítico do mesmo XLSX oficial.

    A função não persiste nem transforma ausência de preço em zero; entrega
    resultados tipados para a próxima etapa de validação e carga.
    """
    path = Path(workbook_path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        available = set(workbook.sheetnames)
    finally:
        workbook.close()

    required = {*PRICE_SHEETS, COMPOSITION_SHEET}
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            "Planilha de referência incompleta; abas ausentes: "
            + ", ".join(missing)
        )

    prices = tuple(
        parse_input_price_table(path, sheet_name, reference=reference)
        for sheet_name in PRICE_SHEETS
    )
    compositions = parse_analytic_compositions(
        path, COMPOSITION_SHEET, reference=reference
    )
    return ReferenceWorkbookResult(
        reference=reference,
        source_file=path.name,
        prices=prices,
        compositions=compositions,
    )
