import json
import multiprocessing
import os

workers_per_core_str = os.getenv("WORKERS_PER_CORE", "1")
use_max_workers = None
if (max_workers := os.getenv("MAX_WORKERS")) is not None:
    use_max_workers = int(max_workers)

host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")

cores = int(os.getenv("MAX_CORES", multiprocessing.cpu_count()))
workers_per_core = float(workers_per_core_str)
default_web_concurrency = workers_per_core * cores
if (web_concur := os.getenv("WEB_CONCURRENCY")):
    web_concurrency = int(web_concur)
    assert web_concurrency > 0
else:
    web_concurrency = max(int(default_web_concurrency), 2)
    if use_max_workers:
        web_concurrency = min(web_concurrency, use_max_workers)

# Gunicorn config variables
loglevel = os.getenv("LOG_LEVEL", "info")
workers = web_concurrency
bind = os.getenv("BIND") or f"{host}:{port}"
errorlog = os.getenv("ERROR_LOG", "-")
worker_tmp_dir = "/dev/shm"
accesslog = os.getenv("ACCESS_LOG", "-")
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "120"))
timeout = int(os.getenv("TIMEOUT", "120"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))


# For debugging and testing
log_data = {
    "loglevel": loglevel,
    "workers": workers,
    "bind": bind,
    "graceful_timeout": graceful_timeout,
    "timeout": timeout,
    "keepalive": keepalive,
    "errorlog": errorlog,
    "accesslog": accesslog,
    # Additional, non-gunicorn variables
    "workers_per_core": workers_per_core,
    "use_max_workers": use_max_workers,
    "host": host,
    "port": port,
}
print(json.dumps(log_data))
