from decimal import Decimal

from openpyxl import Workbook

from getsinapi.extractors.reference_workbook import parse_reference_workbook


UF_CODES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
]


def make_reference_workbook(path):
    workbook = Workbook()
    default = workbook.active
    workbook.remove(default)

    for sheet_name in ("ISD", "ICD", "ISE"):
        sheet = workbook.create_sheet(sheet_name)
        for column, value in enumerate(
            ["Classificação", "Código", "Descrição", "Unidade", "Origem"], start=1
        ):
            sheet.cell(10, column, value)
        for column, uf in enumerate(UF_CODES, start=6):
            sheet.cell(10, column, uf)
        for column, value in enumerate(
            ["01", "1379", "Cimento", "KG", "C"], start=1
        ):
            sheet.cell(11, column, value)
        sheet.cell(11, 18, 10.5)

    analytic = workbook.create_sheet("Analítico")
    for column, value in enumerate(
        ["Grupo", "Código", "Tipo", "Código Item", "Descrição", "Unidade", "Coeficiente", "Situação"],
        start=1,
    ):
        analytic.cell(10, column, value)
    for column, value in enumerate(
        [None, "104658", None, None, "Composição teste", "M2", None, "COM CUSTO"],
        start=1,
    ):
        analytic.cell(11, column, value)
    for column, value in enumerate(
        [None, "104658", "INSUMO", "1379", "Cimento", "KG", 2, None],
        start=1,
    ):
        analytic.cell(12, column, value)

    workbook.save(path)


def test_parse_reference_workbook_integrates_prices_and_compositions(tmp_path):
    path = tmp_path / "SINAPI_Referencia_2026_09.xlsx"
    make_reference_workbook(path)

    result = parse_reference_workbook(path, reference="2026-09")

    assert result.reference == "2026-09"
    assert result.source_file == path.name
    assert [table.table_type for table in result.prices] == ["ISD", "ICD", "ISE"]
    assert all(len(table.records) == 27 for table in result.prices)
    for table in result.prices:
        assert {record.uf for record in table.records} == set(UF_CODES)
        mg_price = next(record.price for record in table.records if record.uf == "MG")
        assert mg_price == Decimal("10.5")
    assert len(result.compositions.compositions) == 1
    assert len(result.compositions.items) == 1


def test_parse_reference_workbook_reports_missing_sheets(tmp_path):
    path = tmp_path / "incomplete.xlsx"
    workbook = Workbook()
    workbook.save(path)

    try:
        parse_reference_workbook(path, reference="2026-09")
    except ValueError as exc:
        assert "abas ausentes" in str(exc)
    else:
        raise AssertionError("Esperava erro por abas obrigatórias ausentes.")


def test_normalization_writes_silver_jsonl_and_manifest(tmp_path):
    from getsinapi.config import Settings
    from getsinapi.pipeline.normalize import normalize_reference_workbook

    source = tmp_path / "SINAPI_Referencia_2026_09.xlsx"
    make_reference_workbook(source)
    settings = Settings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        staging_dir=tmp_path / "data" / "staging",
        processed_dir=tmp_path / "data" / "processed",
        manifest_dir=tmp_path / "data" / "manifests",
        http_timeout=30,
        http_max_retries=1,
        http_backoff_seconds=0.1,
    )

    result = normalize_reference_workbook(
        source, reference="2026-09", settings=settings
    )
    output = settings.processed_dir / "2026-09"

    assert result["counts"]["input_prices"] == 81
    assert result["counts"]["compositions"] == 1
    assert result["counts"]["composition_items"] == 1
    assert (output / "input_prices.jsonl").is_file()
    assert (output / "compositions.jsonl").is_file()
    assert (output / "composition_items.jsonl").is_file()
    assert (output / "normalization-manifest.json").is_file()
