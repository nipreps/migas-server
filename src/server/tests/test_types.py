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
