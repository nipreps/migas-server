#!/bin/env bash

set -e

BUILDTYPE=$1
DEPLOYSERVER=$2

# First update pip
python -m pip install --no-cache-dir pip

case $BUILDTYPE in
release)
    python -m pip install --no-cache-dir pip-tools
    python -m pip-sync stable-requirements.txt
    python -m pip install --no-cache-dir /src
    ;;
latest)
    python -m pip install --no-cache-dir /src
    ;;
latest-test)
    python -m pip install --no-cache-dir /src[test]
    ;;
*)
    echo "Unknown command"
    exit 1
    ;;
esac

if [ "$DEPLOYSERVER" = "gunicorn" ]; then
    python -m pip install --no-cache-dir gunicorn
fi