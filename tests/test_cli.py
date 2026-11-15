import pytest

from getsinapi.cli import _parse_multi_selection


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
