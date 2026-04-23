import pytest

from .. import types


@pytest.mark.parametrize(
    'names,val',
    [
        (['running', 'R'], 'R'),
        (['completed', 'C'], 'C'),
        (['failed', 'F'], 'F'),
        (['suspended', 'S'], 'S'),
    ],
)
def test_status(names, val):
    for name in names:
        assert getattr(types.Status, name).value == val


@pytest.mark.parametrize(
    'value,expected', [('ENOSPC', 'ENOSPC'), (28, '28'), (3.14, '3.14'), (True, 'True'), ('', '')]
)
def test_safestr_parse_value_coerces(value, expected):
    """SafeStr accepts non-string GraphQL inputs from older clients (e.g. errno ints)."""
    assert types.SafeStrScalar.parse_value(value) == expected
    assert types.SafeStrScalar.serialize(value) == expected
