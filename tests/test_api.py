from importlib.metadata import version as distribution_version

from fastapi.testclient import TestClient

from getsinapi import __version__
from getsinapi.api.main import app

client = TestClient(app)


def test_installed_distribution_version_matches_runtime_version():
    assert distribution_version("get-sinapi") == __version__


def test_health_endpoint_reports_api_availability_only():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "get-sinapi-api",
        "version": __version__,
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
            """INSERT INTO input_prices(
                reference, code, description, unit, uf, regime, encargo_mode,
                table_type, price, status, price_origin, source_file,
                source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "1379", "Cimento Portland", "KG", "MG",
             None, "sem_encargos", "ISE", "10.25", "reported",
             "C", "SINAPI.xlsx", "ISE", 11),
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
                unit, coefficient, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "1379", "INSUMO", "Cimento Portland",
             "KG", "2.5", "com_preco", "SINAPI.xlsx", "Analítico", 12),
        )

    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(database))

    summary = client.get("/api/summary", params={"reference": "2026-09"})
    assert summary.status_code == 200
    assert summary.json()["input_prices"] == 2
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
    assert items.json()[0]["status"] == "com_preco"

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

    sem_encargos_prices = client.get(
        "/api/insumos",
        params={"reference": "2026-09", "uf": "MG", "encargo_mode": "sem_encargos"},
    )
    assert sem_encargos_prices.status_code == 200
    assert [row["table_type"] for row in sem_encargos_prices.json()] == ["ISE"]

    sem_encargos_count = client.get(
        "/api/insumos/count",
        params={"reference": "2026-09", "uf": "MG", "encargo_mode": "sem_encargos"},
    )
    assert sem_encargos_count.status_code == 200
    assert sem_encargos_count.json()["total"] == 1

    sem_encargos_cost = client.get(
        "/api/composicoes/104658/custo",
        params={"reference": "2026-09", "uf": "MG", "encargo_mode": "sem_encargos"},
    )
    assert sem_encargos_cost.status_code == 200
    assert sem_encargos_cost.json()["total"] == 25.625

    sem_encargos_budget = client.post(
        "/api/budget",
        json={
            "reference": "2026-09",
            "uf": "MG",
            "regime": None,
            "encargo_mode": "sem_encargos",
            "items": [{"code": "104658", "item_type": "COMPOSICAO", "quantity": "2"}],
        },
    )
    assert sem_encargos_budget.status_code == 200
    assert sem_encargos_budget.json()["total"] == 51.25


def test_data_endpoints_return_service_unavailable_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(tmp_path / "missing.sqlite3"))
    response = client.get("/api/references")
    assert response.status_code == 503


def test_unified_catalog_lists_all_record_families_and_paginates(tmp_path, monkeypatch):
    import sqlite3

    from getsinapi.storage.sqlite import initialize_database

    database = tmp_path / "catalog.sqlite3"
    initialize_database(database)
    with sqlite3.connect(database) as connection:
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
             "C", "SINAPI-2026-09.zip", "ISD", 11),
        )
        connection.execute(
            """INSERT INTO compositions(
                reference, code, description, unit, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "Composição de alvenaria", "M2", "com_custo",
             "SINAPI-2026-09.zip", "Analítico", 11),
        )
        connection.execute(
            """INSERT INTO composition_items(
                reference, composition_code, item_code, item_type, description, unit,
                coefficient, status, source_file, source_sheet, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-09", "104658", "1379", "INSUMO", "Cimento Portland", "KG",
             "2.5", "com_preco", "SINAPI-2026-09.zip", "Analítico", 12),
        )

    monkeypatch.setenv("GETSINAPI_DATABASE_PATH", str(database))
    response = client.get("/api/catalog", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2
    assert payload["items"][0]["reference"] == "2026-09"

    next_page = client.get("/api/catalog", params={"limit": 2, "offset": 2})
    assert next_page.status_code == 200
    assert len(next_page.json()["items"]) == 1

    filtered = client.get("/api/catalog", params={"uf": "MG", "search": "cimento"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2
    assert {row["record_type"] for row in filtered.json()["items"]} == {"INSUMO", "COMPONENTE"}

    compositions = client.get("/api/catalog", params={"record_type": "COMPOSICAO"})
    assert compositions.status_code == 200
    assert compositions.json()["total"] == 1
    assert compositions.json()["items"][0]["code"] == "104658"
