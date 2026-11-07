import json

import pytest
from test_storage import prepare_reference

from getsinapi.storage.sqlite import load_silver_reference


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "not-an-object",
        {"reference": "2026-09"},
    ],
)
def test_load_rejects_malformed_or_incomplete_normalization_manifest(tmp_path, payload):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    manifest = processed / "2026-09" / "normalization-manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    expected_error = TypeError if isinstance(payload, (list, type(None), str)) else ValueError
    with pytest.raises(expected_error, match="manifesto|Manifesto|source_file|objeto"):
        load_silver_reference(processed, reference="2026-09")

    assert not (tmp_path / "data" / "getsinapi.sqlite3").exists()


def test_load_rejects_invalid_json_manifest_with_domain_error(tmp_path):
    processed = tmp_path / "data" / "processed"
    prepare_reference(processed, "2026-09", "002")
    manifest = processed / "2026-09" / "normalization-manifest.json"
    manifest.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="Manifesto Silver"):
        load_silver_reference(processed, reference="2026-09")
