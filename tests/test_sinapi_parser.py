from openpyxl import Workbook

from getsinapi.domain import PriceStatus, Regime
from getsinapi.extractors.sinapi_parser import parse_worksheet


def test_parser_reads_rows_and_preserves_zero_and_missing(tmp_path):
    path = tmp_path / "SINAPI.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Insumos Não Desonerados"
    sheet.append(["UF: MG"])
    sheet.append(["Código", "Descrição", "Unidade", "Preço"])
    sheet.append(["000123", "Cimento", "KG", 0])
    sheet.append(["000124", "Areia", "M3", None])
    workbook.save(path)

    result = parse_worksheet(path, sheet.title, reference="2026-09")

    assert result.header_row == 2
    assert result.regime == Regime.NAO_DESONERADO
    assert result.uf == "MG"
    assert len(result.records) == 2
    assert result.records[0].code == "000123"
    assert result.records[0].price == 0
    assert result.records[0].status == PriceStatus.REPORTED_ZERO
    assert result.records[1].price is None
    assert result.records[1].status == PriceStatus.MISSING


def test_parser_does_not_guess_unknown_layout(tmp_path):
    path = tmp_path / "unknown.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Relatório"
    sheet.append(["Campo A", "Campo B", "Campo C"])
    workbook.save(path)

    result = parse_worksheet(path, sheet.title, reference="2026-09")

    assert result.records == ()
    assert result.header_row is None
    assert result.warnings
