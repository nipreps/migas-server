import pytest

from ..cli import get_parser


def test_parser_defaults():
    opts = get_parser().parse_args([])
    # ensure basic settings are set
    for key in ('host', 'port', 'workers'):
        assert getattr(opts, key)


@pytest.mark.parametrize(
    'input,output',
    [
        ([], None),  # None signals we should check the dynamic default
        (['Hello:There'], [['Hello', 'There']]),
        (['X-Backend-Server:migas', 'X-Test:1'], [['X-Backend-Server', 'migas'], ['X-Test', '1']]),
    ],
)
def test_parser_headers(input, output):
    if input:
        input = ['--headers'] + input
    opts = get_parser().parse_args(input)

    if output is None:
        from .. import get_default_headers

        output = [[k, v] for k, v in get_default_headers().items()]

    assert opts.headers == output
