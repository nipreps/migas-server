# eTelemetry

Usage tracker for your projects!

This is the backend of the etelemetry service. The stack is FastAPI (uvicorn / starlette) + Strawberry (graphql) + PostgreSQL

To play around in the sandbox, visit https://etelemetry2.herokuapp.com/graphql in a browser.



## Usage

### Container
Everything needed to run the eTelemetry service is bundled and usable with `docker compose`.

To start up the server:
1) Clone this repository
2) Travel to the root of the repository
3) Run `docker compose up`

### Local
If you want to install and run the server locally, first install the package

```
$ pip install https://github.com/mgxd/fastapi-telemetry/archive/refs/heads/master.zip
```

* Note: Python 3.10 or higher is required.

Once installed, start the server with `etelemetry-up`.

<details>
<summary>Expand for full options</summary>

```
usage: etelemetry-up [-h] [--host HOST] [--port PORT] [--workers WORKERS] [--reload] [--proxy-headers]

options:
  -h, --help         show this help message and exit
  --host HOST        hostname
  --port PORT        server port
  --workers WORKERS  worker processes
  --reload           Reload app on change (dev only)
  --proxy-headers    Accept incoming proxy headers
```
</details>

### Requirements

Etelemetry is built with [FastAPI](https://fastapi.tiangolo.com/), [Strawberry](https://strawberry.rocks/), [PostgreSQL](https://www.postgresql.org/) and [Redis](https://redis.com/). Additionally, to run the server, some environmental variables must be set up - see the table below.

| Service | Environmental Variable | Alternatives | Required |
| ------- | ---------------------- | -------------| -------- |
| redis | ETELEMETRY_REDIS_URI | n/a | Yes
| postgres | ETELEMETRY_DB_URI | ETELEMETRY_DB_HOSTNAME, ETELEMETRY_DB_PORT, ETELEMETRY_DB_NAME | Yes
