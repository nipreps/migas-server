#!/bin/env bash

BUILDTYPE=$1
DEPLOYSERVER=$2

# First update pip
pip install --no-cache-dir pip

case $BUILDTYPE in
release)
    pip install --no-cache-dir pip-tools
    pip-sync stable-requirements.txt
    pip install --no-cache-dir /src
    ;;
latest)
    pip install --no-cache-dir /src
    ;;
latest-test)
    pip install --no-cache-dir /src[test]
    ;;
*)
    echo "Unknown command"
    exit 1
    ;;
esac

if [ "$DEPLOYSERVER" = "gunicorn" ]; then
    pip install --no-cache-dir gunicorn
fi