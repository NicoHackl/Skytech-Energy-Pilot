"""Tests für die sichere Wertkonvertierung."""

import pytest

from energy_pilot.conversion import safe_float


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1234", 1234.0),
        ("12.5", 12.5),
        (42, 42.0),
        (3.14, 3.14),
        ("  7 ", 7.0),
        ("unavailable", None),
        ("unknown", None),
        ("", None),
        (None, None),
        ("abc", None),
        (True, None),
    ],
)
def test_safe_float(value, expected):
    assert safe_float(value) == expected
