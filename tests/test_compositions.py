from decimal import Decimal

import pytest
from openpyxl import Workbook

from getsinapi.domain import CompositionStatus
from getsinapi.extractors.compositions import parse_analytic_compositions


def make_analytic_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Analítico"
    for column, value in enumerate(
        ["Grupo", "Código", "Tipo", "Código Item", "Descrição", "Unidade", "Coeficiente", "Situação"],
        start=1,
    ):
        sheet.cell(row=10, column=column, value=value)

    # Main composition header.
    values = [None, "104658", "CABECALHO", None, "Composição de teste", "M2", None, "COM CUSTO"]
    for column, value in enumerate(values, start=1):
        sheet.cell(row=11, column=column, value=value)

    # Direct input item.
    values = [None, "104658", "INSUMO", "00001379", "Cimento Portland", "KG", 2.5, None]
    for column, value in enumerate(values, start=1):
        sheet.cell(row=12, column=column, value=value)

    # Nested composition.
    values = [None, "104658", "COMPOSICAO", "87321", "Argamassa", "M3", 0.125, None]
    for column, value in enumerate(values, start=1):
        sheet.cell(row=13, column=column, value=value)

    workbook.save(path)


def test_parse_analytic_composition_and_items_with_traceability(tmp_path):
    path = tmp_path / "SINAPI_Referencia_2026_09.xlsx"
    make_analytic_workbook(path)

    result = parse_analytic_compositions(path, reference="2026-09")

    assert len(result.compositions) == 1
    composition = result.compositions[0]
    assert composition.code == "104658"
    assert composition.status == CompositionStatus.COM_CUSTO
    assert composition.source_row == 11

    assert len(result.items) == 2
    direct_input, nested = result.items
    assert direct_input.item_type == "INSUMO"
    assert direct_input.item_code == "00001379"
    assert direct_input.coefficient == Decimal("2.5")
    assert direct_input.source_row == 12
    assert nested.item_type == "COMPOSICAO"
    assert nested.item_code == "87321"
    assert nested.coefficient == Decimal("0.125")
    assert result.warnings == ()


def test_parser_rejects_invalid_reference_and_unknown_sheet(tmp_path):
    path = tmp_path / "SINAPI_Referencia_2026_09.xlsx"
    make_analytic_workbook(path)

    with pytest.raises(ValueError, match="Competência inválida"):
        parse_analytic_compositions(path, reference="2026-13")

    with pytest.raises(ValueError, match="Aba inexistente"):
        parse_analytic_compositions(path, "Composições", reference="2026-09")


def test_parser_warns_about_missing_and_negative_coefficients(tmp_path):
    path = tmp_path / "SINAPI_Referencia_2026_09.xlsx"
    make_analytic_workbook(path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Analítico"
    headers = ["Grupo", "Código", "Tipo", "Código Item", "Descrição", "Unidade", "Coeficiente", "Situação"]
    for col, value in enumerate(headers, 1):
        sheet.cell(10, col, value)
    rows = [
        [None, "100", "CABECALHO", None, "Composição", "UN", None, "SEM PREÇO"],
        [None, "100", "INSUMO", "200", "Item sem coeficiente", "KG", None, None],
        [None, "100", "INSUMO", "201", "Item com coeficiente negativo", "KG", -1, None],
    ]
    for row_num, row in enumerate(rows, 11):
        for col, value in enumerate(row, 1):
            sheet.cell(row_num, col, value)
    workbook.save(path)

    result = parse_analytic_compositions(path, reference="2026-09")

    assert len(result.compositions) == 1
    assert result.compositions[0].status == CompositionStatus.SEM_PRECO
    assert result.items == ()
    assert any("coeficiente ausente" in warning for warning in result.warnings)
    assert any("coeficiente negativo" in warning for warning in result.warnings)
