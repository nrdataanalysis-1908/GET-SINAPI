from fastapi.testclient import TestClient

from getsinapi.api.main import app

client = TestClient(app)


def test_health_endpoint_reports_api_availability_only():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "get-sinapi-api",
        "version": "0.1.0",
    }


def test_data_endpoints_read_persisted_sinapi_records(tmp_path, monkeypatch):
    import sqlite3

    from getsinapi.storage.sqlite import initialize_database

    database = tmp_path / "getsinapi.sqlite3"
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO source_references(reference, source_file) VALUES (?, ?)",
            ("2026-09", "SINAPI.xlsx"),
        )
        connection.execute(
            """INSERT INTO input_prices(
                reference, code, description, unit, uf, regime, encargo_mode,
                table_type, price, status, price_origin, source_file,
                source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "1379", "Cimento Portland", "KG", "MG",
             "nao_desonerado", "com_encargos", "ISD", "10.25", "reported",
             "C", "SINAPI.xlsx", "ISD", 11),
        )
        connection.execute(
            """INSERT INTO compositions(
                reference, code, description, unit, status,
                source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "Composição teste", "M2", "com_custo",
             "SINAPI.xlsx", "Analítico", 11),
        )
        connection.execute(
            """INSERT INTO composition_items(
                reference, composition_code, item_code, item_type, description,
                unit, coefficient, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "1379", "INSUMO", "Cimento Portland",
             "KG", "2.5", "SINAPI.xlsx", "Analítico", 12),
        )

    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(database))

    summary = client.get("/api/summary", params={"reference": "2026-09"})
    assert summary.status_code == 200
    assert summary.json()["input_prices"] == 1
    assert summary.json()["compositions"] == 1
    assert summary.json()["states"] == 1

    prices = client.get(
        "/api/insumos",
        params={"reference": "2026-09", "uf": "MG", "search": "cimento"},
    )
    assert prices.status_code == 200
    assert prices.json()[0]["price"] == "10.25"

    compositions = client.get(
        "/api/composicoes", params={"reference": "2026-09"}
    )
    assert compositions.status_code == 200
    assert compositions.json()[0]["code"] == "104658"

    items = client.get(
        "/api/composicoes/104658/itens", params={"reference": "2026-09"}
    )
    assert items.status_code == 200
    assert items.json()[0]["coefficient"] == "2.5"

    composition_cost = client.get(
        "/api/composicoes/104658/custo",
        params={"reference": "2026-09", "uf": "MG"},
    )
    assert composition_cost.status_code == 200
    assert composition_cost.json()["total"] == 25.625
    assert composition_cost.json()["status"] == "complete"

    budget = client.post(
        "/api/budget",
        json={
            "reference": "2026-09",
            "uf": "MG",
            "regime": "nao_desonerado",
            "encargo_mode": "com_encargos",
            "items": [{"code": "104658", "item_type": "COMPOSICAO", "quantity": "2"}],
        },
    )
    assert budget.status_code == 200
    assert budget.json()["total"] == 51.25


def test_data_endpoints_return_service_unavailable_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(tmp_path / "missing.sqlite3"))
    response = client.get("/api/references")
    assert response.status_code == 503
