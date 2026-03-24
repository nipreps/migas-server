#!/bin/env bash

set -e

BUILDTYPE=$1
DEPLOYSERVER=$2

case $BUILDTYPE in
release)
    uv sync --locked --no-dev
    ;;
test)
    uv sync --locked --extra test
    ;;
test-latest)
    uv sync --extra test
    ;;
*)
    echo "Unknown build type: $BUILDTYPE"
    exit 1
    ;;
esac

if [ "$DEPLOYSERVER" = "gunicorn" ]; then
    uv pip install --no-cache gunicorn
fi