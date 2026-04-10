from pathlib import Path

__root__ = Path(__file__).parent

try:
    from ._version import __version__
except ImportError:
    __version__ = 'unknown'


def _version_series() -> str:
    from packaging.version import Version

    if __version__ == 'unknown':
        return 'unknown'

    v = Version(__version__)
    return f'{v.major}.{v.minor}'


def get_default_headers() -> dict[str, str]:
    return {'X-Backend-Server': f'migas-{_version_series()}'}
