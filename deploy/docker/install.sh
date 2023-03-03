#!/bin/env bash

BUILDTYPE=$1

case $BUILDTYPE in
release)
    pip install --no-cache-dir pip-tools && pip-sync stable-requirements.txt;;
latest)
    pip install --no-cache-dir /src/migas;;
latest-test)
    pip install --no-cache-dir /src/migas[test];;
*)
    echo "Unknown command" && exit 1;;
esac
