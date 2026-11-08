import pytest
from test_storage import prepare_reference, write_jsonl

from getsinapi.storage.sqlite import load_silver_reference


def test_load_rejects_duplicate_ise_natural_keys_with_null_regime(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    folder = processed / "2026-09"
    duplicate = {
        "reference": "2026-09",
        "code": "001379",
        "description": "Cimento",
        "unit": "KG",
        "uf": "MG",
        "regime": None,
        "encargo_mode": "sem_encargos",
        "table_type": "ISE",
        "price": "10.25",
        "status": "reported",
        "price_origin": "C",
        "source_file": "source.xlsx",
        "source_sheet": "ISE",
        "source_row": 11,
    }
    write_jsonl(folder / "input_prices.jsonl", [duplicate, {**duplicate, "price": "10.50"}])

    # Atualiza o manifesto para que o teste alcance a valida??o da chave natural.
    import hashlib
    import json

    manifest_path = folder / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = folder / "input_prices.jsonl"
    payload = artifact_path.read_bytes()

    artifact = next(
        item for item in manifest["artifacts"]
        if item["file"] == "input_prices.jsonl"
    )
    artifact["records"] = len(payload.splitlines())
    artifact["size_bytes"] = len(payload)
    artifact["sha256"] = hashlib.sha256(payload).hexdigest()

    manifest_path.write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate input-price natural key"):
        load_silver_reference(processed, reference="2026-09")

    assert not (tmp_path / "data" / "getsinapi.sqlite3").exists()
