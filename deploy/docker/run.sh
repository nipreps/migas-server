#!/usr/bin/env bash
set -e

if [ ! -f /.dockerenv ] && [[ -z $GCP_SQL_CONNECTION ]]; then
    echo "Error: not inside a docker container!"
    exit 1
fi

DEFAULT_MODULE_NAME="migas.server.app"
MODULE_NAME=${MODULE_NAME:-$DEFAULT_MODULE_NAME}
VARIABLE_NAME=${VARIABLE_NAME:-"app"}
export APP_MODULE=${APP_MODULE:-"$MODULE_NAME:$VARIABLE_NAME"}

# If there's a prestart.sh script in the /app directory or other path specified, run it before starting
PRE_START_PATH=${PRE_START_PATH:-/src/deploy/docker/prestart.sh}
echo "Checking for prestart script in $PRE_START_PATH"
if [ -f $PRE_START_PATH ] ; then
    echo "Running script $PRE_START_PATH"
    . "$PRE_START_PATH"
fi

case $DEPLOYSERVER in
gunicorn)
    DEFAULT_GUNICORN_CONF=/src/deploy/docker/gunicorn_conf.py
    export GUNICORN_CONF=${GUNICORN_CONF:-$DEFAULT_GUNICORN_CONF}
    export WORKER_CLASS=${WORKER_CLASS:-"uvicorn.workers.UvicornWorker"}
    CMD="python -m gunicorn -k $WORKER_CLASS -c $GUNICORN_CONF $APP_MODULE"
    ;;
uvicorn)
    CMD="python -m uvicorn $APP_MODULE $@"
    ;;
*)
    echo "No deployment server was specified"
    exit 1
    ;;
esac

eval $CMD
