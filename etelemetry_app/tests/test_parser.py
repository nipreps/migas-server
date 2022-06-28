import pytest

from etelemetry_app.main import get_parser


def test_parser_defaults():
    opts = get_parser().parse_args([])
    # ensure basic settings are set
    for key in ('host', 'port', 'workers'):
        assert getattr(opts, key)


@pytest.mark.parametrize(
    'input,output', [
        ([], None),
        (['Hello:There'], [['Hello', 'There']]),
        (['X-Backend-Server:etelemetry', 'X-Test:1'], [['X-Backend-Server', 'etelemetry'], ['X-Test', '1']])
    ]
)
def test_parser_headers(input, output):
    if input:
        input = ['--headers'] + input
    opts = get_parser().parse_args(input)
    assert opts.headers == output

