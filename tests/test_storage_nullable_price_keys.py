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

    with pytest.raises(ValueError, match="duplicate input-price natural key"):
        load_silver_reference(processed, reference="2026-09")

    assert not (tmp_path / "data" / "getsinapi.sqlite3").exists()
