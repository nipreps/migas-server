#!/usr/bin/env python

import sys
import os.path as op


def main():
    sys.path.insert(0, op.abspath('.'))
    from migas_server import __version__
    print(__version__)


if __name__ == '__main__':
    main()