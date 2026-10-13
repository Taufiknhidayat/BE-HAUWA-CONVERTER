import pytest

from app.parsers.text import to_number


@pytest.mark.parametrize('raw, expected', [
    ('Rp 1.250.000', 1250000.0), ('1,5', 1.5), ('2.500,75', 2500.75),
    ('45000', 45000.0), ('12', 12.0), ('', 0.0), (None, 0.0),
])
def test_to_number(raw, expected):
    assert to_number(raw) == expected
