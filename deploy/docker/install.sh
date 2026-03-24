#!/bin/env bash

set -e

BUILDTYPE=$1
DEPLOYSERVER=$2

case $BUILDTYPE in
release)
    uv sync --no-dev
    ;;
latest)
    uv pip install --no-cache /src
    ;;
latest-test)
    uv pip install --no-cache "/src[test]"
    ;;
*)
    echo "Unknown command"
    exit 1
    ;;
esac

if [ "$DEPLOYSERVER" = "gunicorn" ]; then
    uv pip install --no-cache gunicorn
fi