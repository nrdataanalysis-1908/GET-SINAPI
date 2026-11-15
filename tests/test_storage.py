import hashlib
import json
import sqlite3

import pytest

from getsinapi.storage.sqlite import initialize_database, load_silver_reference


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def prepare_reference(root, reference, price_code, *, regime="nao_desonerado", table_type="ISD"):
    folder = root / reference
    folder.mkdir(parents=True)
    write_jsonl(folder / "input_prices.jsonl", [{
        "reference": reference, "code": price_code, "description": "Cimento",
        "unit": "KG", "uf": "MG", "regime": regime,
        "encargo_mode": "sem_encargos" if table_type == "ISE" else "com_encargos",
        "table_type": table_type, "price": "10.25",
        "status": "reported", "price_origin": "C", "source_file": "source.xlsx",
        "source_sheet": table_type, "source_row": 11,
    }])
    write_jsonl(folder / "compositions.jsonl", [{
        "reference": reference, "code": "100", "description": "Composição",
        "unit": "UN", "status": "com_custo", "source_file": "source.xlsx",
        "source_sheet": "Analítico", "source_row": 11,
    }])
    write_jsonl(folder / "composition_items.jsonl", [{
        "reference": reference, "composition_code": "100", "item_code": price_code,
        "item_type": "INSUMO", "description": "Cimento", "unit": "KG",
        "coefficient": "2", "status": "com_preco", "source_file": "source.xlsx",
        "source_sheet": "Analítico", "source_row": 12,
    }])
    artifacts = []
    for filename in ("input_prices.jsonl", "compositions.jsonl", "composition_items.jsonl"):
        payload = (folder / filename).read_bytes()
        artifacts.append({
            "file": filename,
            "records": sum(1 for line in payload.splitlines() if line.strip()),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        })
    manifest = {
        "reference": reference,
        "source_file": f"SINAPI_{reference}.xlsx",
        "artifacts": artifacts,
    }
    (folder / "normalization-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_load_is_idempotent_and_preserves_other_competences(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-08", "001")
    prepare_reference(processed, "2026-09", "002")

    first = load_silver_reference(processed, reference="2026-08")
    second = load_silver_reference(processed, reference="2026-08")
    third = load_silver_reference(processed, reference="2026-09")

    assert first["input_prices"] == 1
    assert second["input_prices"] == 1
    assert third["compositions"] == 1

    database = sqlite3.connect(tmp_path / "data" / "getsinapi.sqlite3")
    try:
        assert database.execute("SELECT COUNT(*) FROM input_prices").fetchone()[0] == 2
        assert database.execute("SELECT COUNT(*) FROM compositions").fetchone()[0] == 2
        assert database.execute(
            "SELECT COUNT(*) FROM composition_items"
        ).fetchone()[0] == 2
    finally:
        database.close()


def test_load_rejects_manifest_competence_mismatch(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    manifest_path = processed / "2026-09" / "normalization-manifest.json"
    manifest_path.write_text(json.dumps({"reference": "2026-08"}), encoding="utf-8")

    try:
        load_silver_reference(processed, reference="2026-09")
    except ValueError as exc:
        assert "diverge" in str(exc)
    else:
        raise AssertionError("Esperava rejeição da competência divergente.")



def test_load_validates_silver_artifact_hash_before_database_write(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    artifact_path = processed / "2026-09" / "compositions.jsonl"
    payload = artifact_path.read_bytes()
    artifact_path.write_bytes(payload.replace(b'"100"', b'"101"', 1))

    try:
        load_silver_reference(processed, reference="2026-09")
    except ValueError as exc:
        assert "SHA-256 divergente" in str(exc)
    else:
        raise AssertionError("Esperava rejeição de artefato Silver adulterado.")

    assert not (tmp_path / "data" / "getsinapi.sqlite3").exists()


def test_load_persists_component_official_status(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")

    load_silver_reference(processed, reference="2026-09")

    database = sqlite3.connect(tmp_path / "data" / "getsinapi.sqlite3")
    try:
        status = database.execute(
            "SELECT status FROM composition_items WHERE reference = '2026-09'"
        ).fetchone()[0]
        assert status == "com_preco"
    finally:
        database.close()


def test_null_regime_price_natural_key_is_unique(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(
        processed, "2026-09", "002", regime=None, table_type="ISE"
    )
    load_silver_reference(processed, reference="2026-09")

    database = sqlite3.connect(tmp_path / "data" / "getsinapi.sqlite3")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """INSERT INTO input_prices(
                    reference, code, description, unit, uf, regime, encargo_mode,
                    table_type, price, status, price_origin, source_file,
                    source_sheet, source_row
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "2026-09", "002", "Cimento", "KG", "MG", None,
                    "sem_encargos", "ISE", "10.25", "reported", "C",
                    "source.xlsx", "ISE", 11,
                ),
            )
    finally:
        database.close()



def test_initialize_database_migrates_existing_component_items_table(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """CREATE TABLE composition_items (
                id INTEGER PRIMARY KEY,
                reference TEXT NOT NULL,
                composition_code TEXT NOT NULL,
                item_code TEXT NOT NULL,
                item_type TEXT NOT NULL,
                description TEXT NOT NULL,
                unit TEXT NOT NULL,
                coefficient TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_sheet TEXT NOT NULL,
                source_row INTEGER NOT NULL
            )"""
        )
    finally:
        connection.close()

    initialize_database(database_path)

    database = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in database.execute("PRAGMA table_info(composition_items)")
        }
        assert "status" in columns
    finally:
        database.close()



def test_existing_natural_key_index_skips_repeated_full_table_audit(tmp_path):
    from getsinapi.storage.sqlite import _ensure_schema, connect

    database_path = tmp_path / "optimized.sqlite3"
    with connect(database_path) as connection:
        _ensure_schema(connection)

    statements = []
    with connect(database_path) as connection:
        connection.set_trace_callback(statements.append)
        _ensure_schema(connection)

    assert not any("GROUP BY reference, code, uf" in sql for sql in statements)


def test_duplicate_price_natural_key_is_rejected_by_sqlite_without_partial_commit(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    folder = processed / "2026-09"
    price_path = folder / "input_prices.jsonl"
    original = price_path.read_text(encoding="utf-8")
    price_path.write_text(original + original, encoding="utf-8")

    manifest_path = folder / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = price_path.read_bytes()
    price_artifact = next(
        item for item in manifest["artifacts"] if item["file"] == "input_prices.jsonl"
    )
    price_artifact["records"] = 2
    price_artifact["size_bytes"] = len(payload)
    price_artifact["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate input-price natural key"):
        load_silver_reference(processed, reference="2026-09")

    database_path = tmp_path / "data" / "getsinapi.sqlite3"
    if database_path.exists():
        database = sqlite3.connect(database_path)
        try:
            assert database.execute("SELECT COUNT(*) FROM input_prices").fetchone()[0] == 0
            assert database.execute("SELECT COUNT(*) FROM source_references").fetchone()[0] == 0
        finally:
            database.close()
