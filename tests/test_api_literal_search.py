import sqlite3

from fastapi.testclient import TestClient

from getsinapi.api.main import app
from getsinapi.storage.sqlite import initialize_database


def test_input_price_search_escapes_percent_and_underscore(tmp_path, monkeypatch):
    database = tmp_path / "getsinapi.sqlite3"
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO source_references(reference, source_file) VALUES (?, ?)",
            ("2026-09", "SINAPI.xlsx"),
        )
        rows = [
            ("A_1", "Material A_1"),
            ("A-1", "Material A-1"),
            ("100%", "Taxa 100%"),
            ("1000", "Código 1000"),
        ]
        for code, description in rows:
            connection.execute(
                """INSERT INTO input_prices(
                    reference, code, description, unit, uf, regime, encargo_mode,
                    table_type, price, status, source_file, source_sheet, source_row
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2026-09", code, description, "UN", "MG", "nao_desonerado",
                 "com_encargos", "ISD", "10.00", "reported",
                 "SINAPI.xlsx", "ISD", 11),
            )

    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(database))
    client = TestClient(app)

    underscore = client.get(
        "/api/insumos",
        params={"reference": "2026-09", "uf": "MG", "search": "A_1"},
    )
    percent = client.get(
        "/api/insumos",
        params={"reference": "2026-09", "uf": "MG", "search": "100%"},
    )

    assert underscore.status_code == 200
    assert [row["code"] for row in underscore.json()] == ["A_1"]
    assert percent.status_code == 200
    assert [row["code"] for row in percent.json()] == ["100%"]
