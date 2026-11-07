from decimal import Decimal

import pytest
from openpyxl import Workbook

from getsinapi.domain import EncargoMode, PriceStatus, Regime
from getsinapi.extractors.price_tables import parse_input_price_table


UFs = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
]


def make_price_workbook(path, sheet_name="ISD"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.cell(row=9, column=1, value="UF")
    for column, uf in enumerate(UFs, start=6):
        sheet.cell(row=9, column=column, value=uf)
    for column, value in enumerate(
        ["Classificação", "Código", "Descrição", "Unidade", "Origem"], start=1
    ):
        sheet.cell(row=10, column=column, value=value)
    sheet.cell(row=11, column=1, value="01")
    sheet.cell(row=11, column=2, value="00001379")
    sheet.cell(row=11, column=3, value="Cimento Portland")
    sheet.cell(row=11, column=4, value="KG")
    sheet.cell(row=11, column=5, value="C")
    sheet.cell(row=11, column=18, value=0)
    sheet.cell(row=11, column=30, value=12.34)
    workbook.save(path)


def test_parse_isd_expands_27_ufs_and_preserves_zero_and_missing(tmp_path):
    path = tmp_path / "SINAPI_ISD_2026_09.xlsx"
    make_price_workbook(path)

    result = parse_input_price_table(path, "ISD", reference="2026-09")

    assert result.table_type == "ISD"
    assert len(result.records) == 27
    mg = next(record for record in result.records if record.uf == "MG")
    assert mg.code == "00001379"
    assert mg.regime == Regime.NAO_DESONERADO
    assert mg.encargo_mode == EncargoMode.COM_ENCARGOS
    assert mg.price == Decimal("0")
    assert mg.status == PriceStatus.REPORTED_ZERO
    sp = next(record for record in result.records if record.uf == "SP")
    assert sp.price == Decimal("12.34")
    assert sp.status == PriceStatus.REPORTED


def test_parser_rejects_unknown_table_type(tmp_path):
    path = tmp_path / "SINAPI_UNKNOWN.xlsx"
    make_price_workbook(path, sheet_name="Relatório")

    with pytest.raises(ValueError, match="Tipo de tabela não identificado"):
        parse_input_price_table(path, "Relatório", reference="2026-09")


def test_ise_is_not_misclassified_as_a_third_desoneration_regime(tmp_path):
    path = tmp_path / "SINAPI_ISE_2026_09.xlsx"
    make_price_workbook(path, sheet_name="ISE")

    result = parse_input_price_table(path, "ISE", reference="2026-09")
    assert result.records[0].regime is None
    assert result.records[0].encargo_mode == EncargoMode.SEM_ENCARGOS



def test_icd_maps_to_desonerated_with_social_charges(tmp_path):
    path = tmp_path / "SINAPI_ICD_2026_09.xlsx"
    make_price_workbook(path, sheet_name="ICD")

    result = parse_input_price_table(path, "ICD", reference="2026-09")

    assert result.records[0].regime == Regime.DESONERADO
    assert result.records[0].encargo_mode == EncargoMode.COM_ENCARGOS


def test_blank_prices_remain_missing(tmp_path):
    path = tmp_path / "SINAPI_ISD_2026_09.xlsx"
    make_price_workbook(path)

    result = parse_input_price_table(path, "ISD", reference="2026-09")
    ac = next(record for record in result.records if record.uf == "AC")

    assert ac.price is None
    assert ac.status == PriceStatus.MISSING


def test_parser_rejects_invalid_reference(tmp_path):
    path = tmp_path / "SINAPI_ISD_2026_09.xlsx"
    make_price_workbook(path)

    with pytest.raises(ValueError, match="Competência inválida"):
        parse_input_price_table(path, "ISD", reference="2026-13")


def test_parser_rejects_invalid_reference_before_reading_rows(tmp_path):
    path = tmp_path / "SINAPI_ISD_2026_09.xlsx"
    make_price_workbook(path)

    with pytest.raises(ValueError, match="Competência inválida"):
        parse_input_price_table(path, "ISD", reference="2026-13")
