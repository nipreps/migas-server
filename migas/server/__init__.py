from pathlib import Path
__root__ = Path(__file__).parent

try:
    from ._version import __version__
except ImportError:
    __version__ = 'unknown'
