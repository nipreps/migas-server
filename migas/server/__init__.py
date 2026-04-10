from pathlib import Path

__root__ = Path(__file__).parent

try:
    from ._version import __version__
except ImportError:
    __version__ = 'unknown'


def version_series() -> str:
    from packaging.version import Version

    if __version__ == 'unknown':
        return 'unknown'

    v = Version(__version__)
    return f'{v.major}.{v.minor}'


def get_default_headers() -> dict[str, str]:
    from .utils import env_to_bool

    return {
        'X-Backend-Server': f'migas@{version_series()}',
        'X-Backend-Geolocation': str(env_to_bool('MIGAS_GEOLOC')).lower(),
        'X-Backend-Mode': 'dev' if env_to_bool('MIGAS_DEV') else 'production',
    }
