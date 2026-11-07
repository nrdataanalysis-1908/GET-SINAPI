import json
import sqlite3

from getsinapi.storage.sqlite import load_silver_reference


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def prepare_reference(root, reference, price_code):
    folder = root / reference
    folder.mkdir(parents=True)
    manifest = {"reference": reference, "source_file": f"SINAPI_{reference}.xlsx"}
    (folder / "normalization-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    write_jsonl(folder / "input_prices.jsonl", [{
        "reference": reference, "code": price_code, "description": "Cimento",
        "unit": "KG", "uf": "MG", "regime": "nao_desonerado",
        "encargo_mode": "com_encargos", "table_type": "ISD", "price": "10.25",
        "status": "reported", "price_origin": "C", "source_file": "source.xlsx",
        "source_sheet": "ISD", "source_row": 11,
    }])
    write_jsonl(folder / "compositions.jsonl", [{
        "reference": reference, "code": "100", "description": "Composição",
        "unit": "UN", "status": "com_custo", "source_file": "source.xlsx",
        "source_sheet": "Analítico", "source_row": 11,
    }])
    write_jsonl(folder / "composition_items.jsonl", [{
        "reference": reference, "composition_code": "100", "item_code": price_code,
        "item_type": "INSUMO", "description": "Cimento", "unit": "KG",
        "coefficient": "2", "source_file": "source.xlsx",
        "source_sheet": "Analítico", "source_row": 12,
    }])


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
