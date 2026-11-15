import pytest

from getsinapi.cli import _parse_multi_selection, _show_header


def test_header_displays_product_identity_and_copyright(capsys, monkeypatch):
    monkeypatch.setattr("getsinapi.cli.ANSI_ENABLED", False)
    _show_header()
    output = capsys.readouterr().out
    assert "GET-SINAPI" in output
    assert "VERSÃO 3.1.1" in output
    assert "© 2026 Nadison Roberto | NR TECH" in output
    assert "LICENÇA     : MIT" in output



@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("1,2", [1, 2]),
        (" 1, 3 ", [1, 3]),
        ("2,2,1", [2, 1]),
        ("A", None),
        ("a", None),
        ("", None),
        ("   ", None),
    ],
)
def test_parse_multi_selection_accepts_multiple_indexes_and_all(answer, expected):
    assert _parse_multi_selection(answer, total=3) == expected


@pytest.mark.parametrize("answer", ["0", "4", "1,,2", "1,x", "-1", "1.5"])
def test_parse_multi_selection_rejects_invalid_values(answer):
    with pytest.raises(ValueError):
        _parse_multi_selection(answer, total=3)
