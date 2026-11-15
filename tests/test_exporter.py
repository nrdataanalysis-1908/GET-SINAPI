import csv
import sqlite3

from openpyxl import load_workbook

from getsinapi.exporter import available_references, export_catalog
from getsinapi.storage.sqlite import initialize_database


def _seed_database(path):
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO source_references(reference, source_file) VALUES (?, ?)",
            ("2026-09", "SINAPI-2026-09.zip"),
        )
        connection.execute(
            """INSERT INTO input_prices(
                reference, code, description, unit, uf, regime, encargo_mode,
                table_type, price, status, price_origin, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "1379", "Cimento Portland", "KG", "MG",
             "nao_desonerado", "com_encargos", "ISD", "10.25", "reported",
             "C", "SINAPI.xlsx", "ISD", 11),
        )
        connection.execute(
            """INSERT INTO compositions(
                reference, code, description, unit, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "Composição de alvenaria", "M2", "com_custo",
             "SINAPI.xlsx", "Analítico", 12),
        )
        connection.execute(
            """INSERT INTO composition_items(
                reference, composition_code, item_code, item_type, description, unit,
                coefficient, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "1379", "INSUMO", "Cimento Portland", "KG",
             "2.5", "com_preco", "SINAPI.xlsx", "Analítico", 13),
        )


def test_export_both_creates_consolidated_and_separate_files(tmp_path):
    database = tmp_path / "getsinapi.sqlite3"
    _seed_database(database)

    assert available_references(database) == ["2026-09"]
    files = export_catalog(database, tmp_path / "exports", file_format="both")

    xlsx = next(path for path in files if path.suffix == ".xlsx")
    csv_files = [path for path in files if path.suffix == ".csv"]
    assert len(csv_files) == 4
    assert any("consolidado" in path.name for path in csv_files)
    assert any("insumos" in path.name for path in csv_files)
    assert any("composicoes" in path.name for path in csv_files)
    assert any("componentes" in path.name for path in csv_files)

    workbook = load_workbook(xlsx, read_only=True, data_only=True)
    assert workbook.sheetnames == ["CONSOLIDADO", "Insumos", "Composicoes", "Componentes"]
    consolidated = list(workbook["CONSOLIDADO"].iter_rows(values_only=True))
    assert len(consolidated) == 4
    assert {row[1] for row in consolidated[1:]} == {"INSUMO", "COMPOSICAO", "COMPONENTE"}

    consolidated_csv = next(path for path in csv_files if "consolidado" in path.name)
    with consolidated_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert len(rows) == 4


def test_export_filters_reference_state_and_category(tmp_path):
    database = tmp_path / "getsinapi.sqlite3"
    _seed_database(database)

    files = export_catalog(
        database,
        tmp_path / "exports",
        file_format="csv",
        references=["2026-09"],
        uf="MG",
        categories=["INSUMO"],
        regime="nao_desonerado",
        encargo_mode="com_encargos",
    )
    assert len(files) == 2
    with files[0].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert len(rows) == 2
    assert rows[1][1] == "INSUMO"
