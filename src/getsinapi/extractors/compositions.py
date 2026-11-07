"""Parser do relatório Analítico oficial de composições SINAPI.

Layout auditado na referência 2026-09:
- Linha 10: cabeçalho das colunas.
- Linha 11 em diante: linhas CABECALHO, COMPOSICAO e INSUMO.
- B: código da composição-pai; C: tipo da linha; D: código do item;
  E: descrição; F: unidade; G: coeficiente; H: situação.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from getsinapi.domain import CompositionStatus
from getsinapi.normalizers import parse_decimal

REFERENCE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
STATUS_MAP = {
    "com custo": CompositionStatus.COM_CUSTO,
    "com preco": CompositionStatus.COM_PRECO,
    "sem custo": CompositionStatus.SEM_CUSTO,
    "sem preco": CompositionStatus.SEM_PRECO,
    "em estudo": CompositionStatus.EM_ESTUDO,
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value).strip().casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized)


def _code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    raw = str(value).strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    return raw


@dataclass(frozen=True, slots=True)
class CompositionRecord:
    reference: str
    code: str
    description: str
    unit: str
    status: CompositionStatus | None
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True, slots=True)
class CompositionItemRecord:
    reference: str
    composition_code: str
    item_code: str
    item_type: str
    description: str
    unit: str
    coefficient: Decimal
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True, slots=True)
class CompositionParseResult:
    compositions: tuple[CompositionRecord, ...]
    items: tuple[CompositionItemRecord, ...]
    warnings: tuple[str, ...]


def parse_analytic_compositions(
    workbook_path: str | Path,
    sheet_name: str = "Analítico",
    *,
    reference: str,
) -> CompositionParseResult:
    """Extrai composições e seus componentes sem preencher dados ausentes."""
    if not REFERENCE_PATTERN.fullmatch(reference):
        raise ValueError("Competência inválida. Informe AAAA-MM.")

    path = Path(workbook_path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Aba inexistente: {sheet_name}")
        sheet = workbook[sheet_name]

        header = [_text(sheet.cell(row=10, column=column).value) for column in range(1, 9)]
        required_headers = {1: "codigo", 2: "tipo", 4: "descricao", 5: "unidade", 6: "coeficiente"}
        if any(not header[index] or expected not in header[index]
               for index, expected in required_headers.items()) or not any(
            "situacao" in value or "status" in value for value in header
        ):
            raise ValueError("Cabeçalho do relatório Analítico não reconhecido na linha 10.")

        compositions: list[CompositionRecord] = []
        items: list[CompositionItemRecord] = []
        warnings: list[str] = []
        known_compositions: set[str] = set()

        for row_number in range(11, (sheet.max_row or 10) + 1):
            parent_code = _code(sheet.cell(row=row_number, column=2).value)
            row_type = _text(sheet.cell(row=row_number, column=3).value)
            item_code = _code(sheet.cell(row=row_number, column=4).value)
            description = str(sheet.cell(row=row_number, column=5).value or "").strip()
            unit = str(sheet.cell(row=row_number, column=6).value or "").strip()
            coefficient_value = sheet.cell(row=row_number, column=7).value
            status_value = _text(sheet.cell(row=row_number, column=8).value)

            if not parent_code and not row_type and not description:
                continue

            if row_type == "cabecalho":
                if not parent_code or not description or not unit:
                    warnings.append(f"Linha {row_number}: cabeçalho de composição incompleto.")
                    continue
                status = STATUS_MAP.get(status_value)
                if status_value and status is None:
                    warnings.append(
                        f"Linha {row_number}: situação não reconhecida: {status_value!r}."
                    )
                if parent_code in known_compositions:
                    warnings.append(
                        f"Linha {row_number}: composição duplicada {parent_code!r}."
                    )
                    continue
                known_compositions.add(parent_code)
                compositions.append(CompositionRecord(
                    reference=reference,
                    code=parent_code,
                    description=description,
                    unit=unit,
                    status=status,
                    source_file=path.name,
                    source_sheet=sheet_name,
                    source_row=row_number,
                ))
                continue

            if row_type not in {"composicao", "insumo"}:
                if row_type:
                    warnings.append(
                        f"Linha {row_number}: tipo de registro não reconhecido: {row_type!r}."
                    )
                continue

            if not parent_code or not item_code or not description or not unit:
                warnings.append(f"Linha {row_number}: componente incompleto ignorado.")
                continue
            try:
                coefficient = parse_decimal(coefficient_value)
            except (TypeError, ValueError):
                warnings.append(f"Linha {row_number}: coeficiente inválido.")
                continue
            if coefficient is None:
                warnings.append(f"Linha {row_number}: coeficiente ausente.")
                continue
            if coefficient < 0:
                warnings.append(f"Linha {row_number}: coeficiente negativo ignorado.")
                continue

            items.append(CompositionItemRecord(
                reference=reference,
                composition_code=parent_code,
                item_code=item_code,
                item_type="COMPOSICAO" if row_type == "composicao" else "INSUMO",
                description=description,
                unit=unit,
                coefficient=coefficient,
                source_file=path.name,
                source_sheet=sheet_name,
                source_row=row_number,
            ))

        orphan_items = [item for item in items if item.composition_code not in known_compositions]
        for item in orphan_items:
            warnings.append(
                f"Linha {item.source_row}: componente sem composição-pai "
                f"{item.composition_code!r}."
            )

        return CompositionParseResult(
            tuple(compositions), tuple(items), tuple(warnings)
        )
    finally:
        workbook.close()
